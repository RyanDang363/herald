"""Phase 3 — Event 1: Patient Intake (INTAKE-*).

Drives the pure intake domain layer against an InMemoryStore (no live Bureau): admissions (id mint +
dedupe), triage (acuity + specialty), specialty-aware bed selection with general fallback, staff
assignment with the R2-A capacity model, and the `orchestrator.run_intake` coordinator that composes
them in INTAKE-FLOW order and owns the patient status transitions (decision Gap 8).

The running Bureau executes the same pure functions from its message handlers; this file verifies the
logic + state outcomes. Each test traces to an EARS spec id.
"""

from er_twin.agents import admissions, bed, doctor, nurse, orchestrator, patient, triage
from er_twin.storage import InMemoryStore


def _clean_store() -> InMemoryStore:
    store = InMemoryStore()
    for module in (patient, bed, nurse, doctor):
        module.init_state(store)
    return store


CHEST_PAIN = ("Jordan Lee", "chest pain", {"spo2": 96, "heart_rate": 112})


# --- Admissions: record creation, id minting, dedupe (INTAKE-FLOW-002, INTAKE-IDEM-001) ---


def test_admissions_creates_waiting_record_with_minted_id():
    # @spec INTAKE-FLOW-002
    store = _clean_store()
    pid, record, created = admissions.intake(store, *CHEST_PAIN)
    assert created is True
    assert pid == "p1"
    assert record["status"] == "waiting"
    assert store.get("er:patient:p1")["chief_complaint"] == "chest pain"
    # second, different patient gets the next id
    pid2, _, _ = admissions.intake(store, "Sam Rivera", "ankle sprain", {})
    assert pid2 == "p2"


def test_admissions_dedupes_active_patient():
    # @spec INTAKE-IDEM-001
    store = _clean_store()
    pid1, _, created1 = admissions.intake(store, *CHEST_PAIN)
    pid2, _, created2 = admissions.intake(store, *CHEST_PAIN)
    assert created1 is True and created2 is False
    assert pid1 == pid2
    assert store.list_ids("patient") == ["p1"]  # no second record


# --- Triage: acuity + specialty, ESI range, discharge guard (INTAKE-FLOW-004, STATE-002, DOMAIN-003) ---


def test_triage_assigns_acuity_and_specialty():
    # @spec INTAKE-FLOW-004
    # @spec INTAKE-STATE-002
    store = _clean_store()
    admissions.intake(store, *CHEST_PAIN)
    acuity, specialty = triage.triage(store, "p1")
    assert acuity == 2 and specialty == "cardiology"
    assert 1 <= acuity <= 5
    assert store.get("er:patient:p1")["acuity"] == 2
    assert store.get("er:patient:p1")["specialty"] == "cardiology"


def test_triage_refuses_discharged_patient():
    # @spec DOMAIN-STATE-003
    store = _clean_store()
    store.set("er:patient:p9", {"id": "p9", "status": "discharged", "chief_complaint": "x"})
    try:
        triage.triage(store, "p9")
        raised = False
    except ValueError:
        raised = True
    assert raised is True


# --- Bed selection: specialty match + general fallback + none (INTAKE-FLOW-006, ERR-001, ERR-002) ---


def test_bed_selection_prefers_specialty_match():
    # @spec INTAKE-FLOW-006
    store = _clean_store()
    assert bed.find_available_bed(store, "cardiology") == "bed1"  # bed1 is the cardiology bed


def test_bed_selection_falls_back_to_general():
    # @spec INTAKE-ERR-001
    store = _clean_store()
    bed.assign_patient_to_bed(store, "pX", "bed1")  # occupy the only cardiology bed
    # no cardiology bed free -> general fallback (bed2 or bed3)
    assert bed.find_available_bed(store, "cardiology") in ("bed2", "bed3")


def test_bed_selection_none_when_full():
    # @spec INTAKE-ERR-002
    store = _clean_store()
    for i, bid in enumerate(bed.BEDS, start=1):
        bed.assign_patient_to_bed(store, f"pX{i}", bid)
    assert bed.find_available_bed(store, "general") is None


# --- Staff assignment: capacity + idempotency (INTAKE-FLOW-008/011, IDEM-002, decision R2-A) ---


def test_nurse_single_patient_capacity():
    # @spec INTAKE-FLOW-008
    store = _clean_store()
    assert nurse.assign_nurse(store, "nurse1", "p1") is True
    assert store.get("er:nurse:nurse1")["available"] is False
    # idempotent re-assign of the same patient -> True, no duplicate
    assert nurse.assign_nurse(store, "nurse1", "p1") is True
    assert store.get("er:nurse:nurse1")["assignments"] == ["p1"]
    # a busy nurse rejects a different patient
    assert nurse.assign_nurse(store, "nurse1", "p2") is False


def test_doctor_load_capacity():
    # @spec INTAKE-FLOW-011
    store = _clean_store()
    assert doctor.assign_doctor(store, "doc1", "p1") is True
    assert store.get("er:doctor:doc1")["load"] == 1
    assert store.get("er:doctor:doc1")["available"] is True  # still under cap
    # idempotent
    assert doctor.assign_doctor(store, "doc1", "p1") is True
    assert store.get("er:doctor:doc1")["load"] == 1
    # fill to cap (3) -> unavailable
    doctor.assign_doctor(store, "doc1", "p2")
    doctor.assign_doctor(store, "doc1", "p3")
    assert store.get("er:doctor:doc1")["load"] == 3
    assert store.get("er:doctor:doc1")["available"] is False


# --- Full intake flow via the coordinator (INTAKE-FLOW-009/010, STATE-001, ERR-003/004, BIND-003) ---


def test_run_intake_happy_path_chest_pain():
    # @spec INTAKE-FLOW-009
    # @spec INTAKE-FLOW-010
    # @spec INTAKE-STATE-001
    store = _clean_store()
    result = orchestrator.run_intake(store, *CHEST_PAIN)

    assert result["patient_id"] == "p1"
    assert result["error"] is None
    assert result["acuity"] == 2 and result["specialty"] == "cardiology"
    assert result["bed_id"] == "bed1"            # cardiology bed
    assert result["nurse_id"] == "nurse1"
    assert result["doctor_id"] == "doc1"         # acuity <= 2 -> doctor paged, specialty-matched
    assert store.get("er:patient:p1")["status"] == "admitted"
    assert store.get("er:patient:p1")["care_team"] == ["nurse1", "doc1"]
    # confirmation names patient + care team via display names (INTAKE-FLOW-009)
    assert "Jordan Lee" in result["confirmation"]
    assert "ESI-2" in result["confirmation"]
    assert "Dr. Smith" in result["confirmation"]  # doc1 display name


def test_run_intake_no_bed_leaves_patient_waiting():
    # @spec INTAKE-ERR-002
    store = _clean_store()
    for i, bid in enumerate(bed.BEDS, start=1):
        bed.assign_patient_to_bed(store, f"pX{i}", bid)
    result = orchestrator.run_intake(store, *CHEST_PAIN)
    assert result["error"] == "no_bed_available"
    assert result["bed_id"] is None
    assert store.get("er:patient:p1")["status"] == "waiting"
    assert "no bed" in result["confirmation"].lower()


def test_run_intake_no_nurse_still_admits():
    # @spec INTAKE-ERR-003
    store = _clean_store()
    for n in nurse.NURSES:
        store.update(f"er:nurse:{n}", {"available": False})
    result = orchestrator.run_intake(store, *CHEST_PAIN)
    assert result["error"] is None
    assert result["bed_id"] is not None       # admitted to a bed
    assert result["nurse_id"] is None
    assert store.get("er:patient:p1")["status"] == "admitted"
    assert "no staff" in result["confirmation"].lower()


def test_run_intake_high_acuity_no_doctor_notes_it():
    # @spec INTAKE-ERR-004
    store = _clean_store()
    for d in doctor.DOCTORS:
        store.update(f"er:doctor:{d}", {"available": False, "load": doctor.DOCTOR_LOAD_CAP})
    result = orchestrator.run_intake(store, *CHEST_PAIN)
    assert result["error"] is None
    assert result["nurse_id"] is not None
    assert result["doctor_id"] is None
    assert "no doctor" in result["confirmation"].lower()


def test_run_intake_pool_full_reports_capacity():
    # @spec INTAKE-BIND-003
    store = _clean_store()
    for slot in range(1, patient.PATIENT_COUNT + 1):
        patient.bind_slot(store, slot, f"existing{slot}", {"id": f"existing{slot}", "status": "admitted"})
    result = orchestrator.run_intake(store, *CHEST_PAIN)
    assert result["error"] == "patient_capacity_reached"
    assert result["bed_id"] is None
    assert store.get("er:patient:p1")["status"] == "waiting"
    assert "capacity" in result["confirmation"].lower()


def test_run_intake_is_idempotent_on_duplicate():
    # @spec INTAKE-IDEM-001
    store = _clean_store()
    first = orchestrator.run_intake(store, *CHEST_PAIN)
    second = orchestrator.run_intake(store, *CHEST_PAIN)
    assert first["patient_id"] == second["patient_id"] == "p1"
    assert store.list_ids("patient") == ["p1"]   # no duplicate record
    assert second["created"] is False
