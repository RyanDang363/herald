"""Event registry and MRN-driven intake flow tests."""

from er_twin import active_events
from er_twin.agents import admissions, bed, doctor, nurse, patient, triage
from er_twin.events.helpers import extract_mrn, synthesize_vitals
from er_twin.events.intake_flow import commit_intake_assignments, plan_intake_proposal
from er_twin.events.registry import EVENT_REGISTRY
from er_twin.storage import InMemoryStore


def _clean_store() -> InMemoryStore:
    store = InMemoryStore()
    for module in (patient, bed, nurse, doctor):
        module.init_state(store)
    return store


def test_registry_has_core_handlers():
    # @spec EVREG-FLOW-001
    assert set(EVENT_REGISTRY) >= {"intake", "oxygen", "summary", "discharge", "resolve", "ping"}


def test_extract_mrn_from_chat():
    # @spec INTAKE-MRN-001
    assert extract_mrn("patient intake MRN-0005 chest pain") == "MRN-0005"


def test_synthesize_vitals_deterministic():
    # @spec INTAKE-MRN-003
    v1 = synthesize_vitals("MRN-0005")
    v2 = synthesize_vitals("MRN-0005")
    assert v1 == v2 and "heart_rate" in v1


def test_plan_intake_proposal_triages_without_assigning_bed():
    # @spec ASSIGN-FLOW-001 — plan is now fully read-only; no patient record created yet.
    store = _clean_store()
    plan = plan_intake_proposal(store, "Casey Lee", "chest pain", synthesize_vitals("MRN-0001"), "MRN-0001")
    assert plan["acuity"] == 2
    assert plan["proposed"]["bed_id"] is not None
    assert plan.get("error") is None
    # No patient record written to the store during planning.
    assert store.get("er:patient:p1") == {}


def test_commit_full_intake_creates_patient_and_assigns_resources():
    # @spec ASSIGN-FLOW-002 @spec ASSIGN-STATE-001
    from er_twin.events.intake_flow import commit_full_intake
    store = _clean_store()
    vitals = synthesize_vitals("MRN-0001")
    outcome = commit_full_intake(
        store, "Casey Lee", "chest pain", vitals, "MRN-0001",
        "bed1", "nurse1", "doctor1",
    )
    assert outcome["bed_id"] == "bed1"
    assert store.get("er:nurse:nurse1")["location"] == "bed1"
    assert store.get("er:patient:p1")["status"] == "admitted"


def test_commit_intake_assignments_moves_staff():
    # @spec ASSIGN-FLOW-002 @spec ASSIGN-STATE-001 — uses pre-created patient (test helper path)
    from er_twin.agents import admissions
    store = _clean_store()
    patient_id, _, _ = admissions.intake(store, "Casey Lee", "chest pain", synthesize_vitals("MRN-0001"), "MRN-0001")
    slot = patient.find_idle_slot(store)
    patient.bind_slot(store, slot, patient_id, store.get(f"er:patient:{patient_id}"))
    store.update(f"er:patient:{patient_id}", {"status": "in_triage"})
    triage.triage(store, patient_id)
    outcome = commit_intake_assignments(
        store, patient_id, "bed1", "nurse1", "doctor1",
    )
    assert outcome["bed_id"] == "bed1"
    assert store.get("er:nurse:nurse1")["location"] == "bed1"
    assert store.get(f"er:patient:{patient_id}")["status"] == "admitted"


def test_active_event_lifecycle():
    # @spec RESOLVE-FLOW-001
    store = _clean_store()
    evt_id = active_events.create_active_event(store, "intake", "test intake", patient_id="p1")
    listed = active_events.list_active_events(store)
    assert len(listed) == 1 and listed[0]["id"] == evt_id
    rec = active_events.resolve_active_event(store, evt_id)
    assert rec is not None
    assert active_events.list_active_events(store) == []
