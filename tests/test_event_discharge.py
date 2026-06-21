"""Discharge flow tests."""

from er_twin.agents import bed, doctor, nurse, patient
from er_twin.agents import admissions, triage
from er_twin.events.discharge_flow import (
    commit_discharge,
    find_discharge_candidate,
    mark_discharged,
    plan_discharge_proposal,
    release_patient_resources,
)
from er_twin.events.intake_flow import commit_full_intake, plan_intake_proposal
from er_twin.events.helpers import synthesize_vitals
from er_twin.storage import InMemoryStore


def _clean_store() -> InMemoryStore:
    store = InMemoryStore()
    for module in (patient, bed, nurse, doctor):
        module.init_state(store)
    return store


def _admitted_patient(store: InMemoryStore, mrn: str = "MRN-0001") -> dict:
    """Admit a patient end-to-end (plan → commit) and return the commit outcome."""
    plan = plan_intake_proposal(store, "Casey Lee", "chest pain", synthesize_vitals(mrn), mrn)
    outcome = commit_full_intake(
        store, "Casey Lee", "chest pain", synthesize_vitals(mrn), mrn,
        plan["proposed"]["bed_id"], plan["proposed"]["nurse_id"], plan["proposed"]["doctor_id"],
    )
    return outcome


def test_find_discharge_candidate_by_mrn():
    # @spec DISCHARGE-FLOW-001
    store = _clean_store()
    admissions.intake(store, "Casey Lee", "chest pain", synthesize_vitals("MRN-0001"), "MRN-0001")
    triage.triage(store, "p1")
    rec = find_discharge_candidate(store, "MRN-0001")
    assert rec is not None and rec["id"] == "p1"


def test_plan_discharge_proposal_recommends_care_team():
    # @spec DISCHARGE-FLOW-002
    store = _clean_store()
    intake_outcome = _admitted_patient(store)
    proposal = plan_discharge_proposal(store, "MRN-0001")
    assert proposal["error"] is None
    assert proposal["proposed"]["nurse_id"] == intake_outcome["nurse_id"]
    assert proposal["proposed"]["doctor_id"] == intake_outcome["doctor_id"]
    nurse_tags = {n["id"]: n["tag"] for n in proposal["available"]["nurses"]}
    assert nurse_tags[intake_outcome["nurse_id"]] == "care team"
    assert any(n["tag"] == "available" for n in proposal["available"]["nurses"])


def test_commit_discharge_keeps_bed_until_resolve():
    # @spec DISCHARGE-STATE-002
    store = _clean_store()
    intake_outcome = _admitted_patient(store)
    patient_id = intake_outcome["patient_id"]
    bed_id = intake_outcome["bed_id"]
    nurse_id = intake_outcome["nurse_id"]

    outcome = commit_discharge(store, patient_id, nurse_id, intake_outcome["doctor_id"])
    assert store.get(patient.patient_key(patient_id))["status"] == "discharged"
    assert store.get(bed.bed_key(bed_id))["status"] == "occupied"
    assert store.get(nurse.nurse_key(nurse_id))["available"] is False
    assert "confirmation" in outcome

    release_patient_resources(store, patient_id)
    assert store.get(bed.bed_key(bed_id))["status"] == "available"
    assert store.get(nurse.nurse_key(nurse_id))["available"] is True


def test_release_patient_resources_frees_staff():
    # @spec DISCHARGE-STATE-001
    store = _clean_store()
    outcome = _admitted_patient(store)
    mark_discharged(store, outcome["patient_id"])
    release_patient_resources(store, outcome["patient_id"])
    assert store.get("er:nurse:nurse1")["available"] is True
    assert store.get("er:bed:bed1")["status"] == "available"
