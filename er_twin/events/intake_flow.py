"""Interactive intake flow — propose (read-only) then commit on confirm."""

from __future__ import annotations

from er_twin.agents import admissions, bed, doctor, nurse, patient, triage
from er_twin.display import DISPLAY_NAMES
from er_twin.ehr import find_active_patient_by_mrn
from er_twin.storage import StorageInterface


def plan_intake_proposal(
    store: StorageInterface,
    name: str,
    chief_complaint: str,
    vitals: dict,
    mrn: str,
) -> dict:
    """Compute triage + available resources without writing any state.

    No patient record is created here — the dashboard KPIs and patient list are
    unchanged until the admin confirms the assignment.
    """
    # Read-only duplicate check: MRN already active in the ER?
    if mrn and find_active_patient_by_mrn(store, mrn) is not None:
        return {"error": "duplicate", "mrn": mrn, "name": name}

    # Patient pool capacity check (read-only)
    if patient.find_idle_slot(store) is None:
        return {"error": "patient_capacity_reached", "mrn": mrn, "name": name}

    # Pure triage — no store write
    acuity, specialty = triage.assess(chief_complaint)

    # Recommended first-available resources (read-only)
    bed_id = bed.find_available_bed(store, specialty)
    nurse_id = nurse.find_available_nurse(store)
    doctor_id = None if acuity > 2 else doctor.find_available_doctor(store, specialty)

    # All options for the proposal card
    available_beds = [
        {"id": bid, "specialty": store.get(bed.bed_key(bid)).get("specialty", "")}
        for bid in bed.BEDS
        if store.get(bed.bed_key(bid)).get("status") == "available"
    ]
    available_nurses = [
        {"id": nid, "name": DISPLAY_NAMES.get(nid, nid)}
        for nid in nurse.NURSES
        if store.get(nurse.nurse_key(nid)).get("available")
    ]
    available_doctors = [
        {
            "id": did,
            "name": DISPLAY_NAMES.get(did, did),
            "specialty": store.get(doctor.doctor_key(did)).get("specialty", ""),
            "load": store.get(doctor.doctor_key(did)).get("load", 0),
        }
        for did in doctor.DOCTORS
        if store.get(doctor.doctor_key(did)).get("available")
    ] if acuity <= 2 else []

    return {
        "error": None,
        "name": name,
        "mrn": mrn,
        "acuity": acuity,
        "specialty": specialty,
        "proposed": {"bed_id": bed_id, "nurse_id": nurse_id, "doctor_id": doctor_id},
        "available": {
            "beds": available_beds,
            "nurses": available_nurses,
            "doctors": available_doctors,
        },
    }


def commit_full_intake(
    store: StorageInterface,
    name: str,
    chief_complaint: str,
    vitals: dict,
    mrn: str,
    bed_id: str | None,
    nurse_id: str | None,
    doctor_id: str | None,
    on_milestone=None,
) -> dict:
    """Create the patient record and commit all assignments on admin confirm.

    This is the first state-mutating step for intake — nothing is written to
    the store until the admin confirms via chat or the dashboard card.
    """
    milestones: list[dict] = []

    def log(action: str, target: str | None = None, **detail) -> None:
        milestones.append({"action": action, "target": target, "detail": detail})
        if on_milestone is not None:
            on_milestone(action, target, detail)

    # Create patient record (admissions handles MRN dedup + EHR enrichment)
    patient_id, record, created = admissions.intake(store, name, chief_complaint, vitals, mrn)
    if not created:
        return {
            "patient_id": patient_id,
            "error": "duplicate",
            "confirmation": f"{name} ({mrn}) is already active in the ER.",
            "milestones": milestones,
        }

    slot = patient.find_idle_slot(store)
    if slot is None:
        return {
            "patient_id": patient_id,
            "error": "patient_capacity_reached",
            "confirmation": f"{name} is waiting — patient capacity reached.",
            "milestones": milestones,
        }
    patient.bind_slot(store, slot, patient_id, store.get(patient.patient_key(patient_id)))

    # Triage (deterministic; uses same assess() logic as plan_intake_proposal)
    store.update(patient.patient_key(patient_id), {"status": "in_triage"})
    acuity, specialty = triage.triage(store, patient_id)

    result: dict = {
        "patient_id": patient_id,
        "bed_id": None,
        "nurse_id": None,
        "doctor_id": None,
        "status": "in_triage",
        "milestones": milestones,
        "error": None,
    }

    if not bed_id:
        log("no_bed_available", patient_id)
        store.update(patient.patient_key(patient_id), {"status": "waiting"})
        result["error"] = "no_bed_available"
        result["status"] = "waiting"
        result["confirmation"] = f"No bed available — {name} remains waiting (ESI-{acuity})."
        return result

    bed.assign_patient_to_bed(store, patient_id, bed_id)
    log("bed_assigned", bed_id, patient=patient_id)
    store.update(patient.patient_key(patient_id), {"status": "admitted"})
    result["bed_id"] = bed_id
    result["status"] = "admitted"

    if nurse_id and nurse.assign_nurse(store, nurse_id, patient_id, bed_id=bed_id):
        log("nurse_assigned", nurse_id, patient=patient_id)
        result["nurse_id"] = nurse_id
    else:
        log("no_nurse_available", patient_id)

    if doctor_id and acuity is not None and acuity <= 2:
        if doctor.assign_doctor(store, doctor_id, patient_id, bed_id=bed_id):
            log("doctor_paged", doctor_id, patient=patient_id)
            result["doctor_id"] = doctor_id
        else:
            log("no_doctor_available", patient_id)

    team = [sid for sid in (result["nurse_id"], result["doctor_id"]) if sid]
    store.update(patient.patient_key(patient_id), {"care_team": team})
    log("intake_complete", patient_id)
    result["confirmation"] = _format_confirmation(name, acuity, specialty, bed_id, result["nurse_id"], result["doctor_id"])
    return result


def commit_intake_assignments(
    store: StorageInterface,
    patient_id: str,
    bed_id: str | None,
    nurse_id: str | None,
    doctor_id: str | None,
    on_milestone=None,
) -> dict:
    """Assign bed/nurse/doctor to an already-created patient (used by tests only)."""
    milestones: list[dict] = []

    def log(action: str, target: str | None = None, **detail) -> None:
        milestones.append({"action": action, "target": target, "detail": detail})
        if on_milestone is not None:
            on_milestone(action, target, detail)

    record = store.get(patient.patient_key(patient_id))
    name = record.get("name", patient_id)
    acuity = record.get("acuity")
    specialty = record.get("specialty", "general")
    result: dict = {
        "patient_id": patient_id,
        "bed_id": None,
        "nurse_id": None,
        "doctor_id": None,
        "status": record.get("status"),
        "milestones": milestones,
        "error": None,
    }

    if not bed_id:
        log("no_bed_available", patient_id)
        store.update(patient.patient_key(patient_id), {"status": "waiting"})
        result["error"] = "no_bed_available"
        result["status"] = "waiting"
        result["confirmation"] = f"No bed available — {name} remains waiting (ESI-{acuity})."
        return result

    bed.assign_patient_to_bed(store, patient_id, bed_id)
    log("bed_assigned", bed_id, patient=patient_id)
    store.update(patient.patient_key(patient_id), {"status": "admitted"})
    result["bed_id"] = bed_id
    result["status"] = "admitted"

    if nurse_id and nurse.assign_nurse(store, nurse_id, patient_id, bed_id=bed_id):
        log("nurse_assigned", nurse_id, patient=patient_id)
        result["nurse_id"] = nurse_id
    else:
        log("no_nurse_available", patient_id)

    if doctor_id and acuity is not None and acuity <= 2:
        if doctor.assign_doctor(store, doctor_id, patient_id, bed_id=bed_id):
            log("doctor_paged", doctor_id, patient=patient_id)
            result["doctor_id"] = doctor_id
        else:
            log("no_doctor_available", patient_id)

    team = [sid for sid in (result["nurse_id"], result["doctor_id"]) if sid]
    store.update(patient.patient_key(patient_id), {"care_team": team})
    log("intake_complete", patient_id)
    result["confirmation"] = _format_confirmation(name, acuity, specialty, bed_id, result["nurse_id"], result["doctor_id"])
    return result


def _format_confirmation(name, acuity, specialty, bed_id, nurse_id, doctor_id) -> str:
    from er_twin.display import display

    head = f"Admitted {name}. Triage ESI-{acuity}."
    if nurse_id:
        care = f"Assigned {display(bed_id)} + {display(nurse_id)}"
    else:
        care = f"Assigned {display(bed_id)}; no staff available"
    if doctor_id:
        care += f"; paged {display(doctor_id)} ({specialty})."
    elif acuity is not None and acuity <= 2:
        care += "; no doctor available."
    else:
        care += "."
    return f"{head} {care}"
