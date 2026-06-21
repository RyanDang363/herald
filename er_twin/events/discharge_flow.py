"""Discharge (outtake) flow — propose sign-off, mark discharged, release on resolve."""

from __future__ import annotations

from er_twin.agents import bed, doctor, nurse, patient
from er_twin.display import DISPLAY_NAMES
from er_twin.ehr import find_active_patient_by_mrn
from er_twin.storage import StorageInterface


def find_discharge_candidate(store: StorageInterface, mrn: str) -> dict | None:
    """Return the active patient record for an MRN, or None."""
    patient_id = find_active_patient_by_mrn(store, mrn)
    if not patient_id:
        return None
    rec = store.get(patient.patient_key(patient_id))
    return rec if rec.get("status") != "discharged" else None


def mark_discharged(store: StorageInterface, patient_id: str) -> dict:
    """Mark patient discharged; physical cleanup happens on event resolve."""
    key = patient.patient_key(patient_id)
    record = store.get(key)
    store.update(key, {"status": "discharged"})
    return {**record, "status": "discharged"}


def _first_care_team_member(care_team: list[str], prefix: str) -> str | None:
    for member in care_team:
        if member.startswith(prefix):
            return member
    return None


def _staff_option(
    store: StorageInterface,
    staff_id: str,
    *,
    tag: str,
    is_nurse: bool,
) -> dict:
    if is_nurse:
        rec = store.get(nurse.nurse_key(staff_id))
        return {
            "id": staff_id,
            "name": DISPLAY_NAMES.get(staff_id, staff_id),
            "tag": tag,
            "available": bool(rec.get("available")),
        }
    rec = store.get(doctor.doctor_key(staff_id))
    return {
        "id": staff_id,
        "name": DISPLAY_NAMES.get(staff_id, staff_id),
        "specialty": rec.get("specialty", ""),
        "load": rec.get("load", 0),
        "tag": tag,
        "available": bool(rec.get("available")),
    }


def plan_discharge_proposal(store: StorageInterface, mrn: str) -> dict:
    """Build discharge sign-off proposal without marking discharged."""
    rec = find_discharge_candidate(store, mrn)
    if rec is None:
        return {"error": "not_found", "mrn": mrn}

    patient_id = rec.get("id", "")
    care_team = list(rec.get("care_team", []))
    bed_id = rec.get("assigned_bed")
    nurse_id = _first_care_team_member(care_team, "nurse")
    doctor_id = _first_care_team_member(care_team, "doc")

    team_nurses = {m for m in care_team if m.startswith("nurse")}
    team_doctors = {m for m in care_team if m.startswith("doc")}

    available_nurses: list[dict] = []
    for nid in care_team:
        if nid.startswith("nurse"):
            available_nurses.append(_staff_option(store, nid, tag="care team", is_nurse=True))
    for nid in nurse.NURSES:
        if nid not in team_nurses:
            available_nurses.append(_staff_option(store, nid, tag="available", is_nurse=True))

    available_doctors: list[dict] = []
    for did in care_team:
        if did.startswith("doc"):
            available_doctors.append(_staff_option(store, did, tag="care team", is_nurse=False))
    for did in doctor.DOCTORS:
        if did not in team_doctors:
            available_doctors.append(_staff_option(store, did, tag="available", is_nurse=False))

    return {
        "patient_id": patient_id,
        "name": rec.get("name", ""),
        "mrn": mrn,
        "bed_id": bed_id,
        "care_team": care_team,
        "error": None,
        "proposed": {"nurse_id": nurse_id, "doctor_id": doctor_id},
        "available": {
            "beds": [],
            "nurses": available_nurses,
            "doctors": available_doctors,
        },
    }


def commit_discharge(
    store: StorageInterface,
    patient_id: str,
    nurse_id: str | None,
    doctor_id: str | None,
) -> dict:
    """Mark patient discharged and record sign-off staff; bed/care_team freed on resolve."""
    from er_twin.display import display

    record = mark_discharged(store, patient_id)
    signoff = [sid for sid in (nurse_id, doctor_id) if sid]
    store.update(patient.patient_key(patient_id), {"discharge_signed_by": signoff})

    name = record.get("name", patient_id)
    mrn = record.get("mrn", "")
    bed_id = record.get("assigned_bed")
    team_parts = [display(sid) for sid in signoff]
    team_text = " + ".join(team_parts) if team_parts else "no staff sign-off"
    bed_text = display(bed_id) if bed_id else "waiting area"
    confirmation = (
        f"Discharge confirmed for {name} ({mrn}) from {bed_text}. "
        f"Signed off by {team_text}. Resolve to free bed and staff."
    )
    return {"confirmation": confirmation, "signoff": signoff}


def release_patient_resources(store: StorageInterface, patient_id: str) -> None:
    """Free bed, nurse, and doctor tied to a discharged patient."""
    rec = store.get(patient.patient_key(patient_id))
    bed_id = rec.get("assigned_bed")
    if bed_id:
        bed.release_bed(store, bed_id)
    for member in rec.get("care_team", []):
        if member.startswith("nurse"):
            nurse.release_nurse(store, member, patient_id)
        elif member.startswith("doc"):
            doctor.release_doctor(store, member, patient_id)
