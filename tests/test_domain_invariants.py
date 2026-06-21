"""Phase 2 — cross-cutting domain invariants (DOMAIN-STATE-001/002/003).

The confirmed domain constraints (DK1–DK3) are enforced by pure, store-operating guard functions so
they are verifiable without a live Bureau. Each guard rejects a violating mutation rather than
raising — the agent handlers (Phase 3) surface the rejection to the chat.
"""

from er_twin.agents import bed, patient
from er_twin.storage import InMemoryStore


def _store() -> InMemoryStore:
    store = InMemoryStore()
    bed.init_state(store)
    patient.init_state(store)
    return store


def test_bed_not_occupied_by_two_patients():
    # @spec DOMAIN-STATE-001
    store = _store()
    assert bed.assign_patient_to_bed(store, "p1", "bed1") is True
    # A second, different patient cannot take an occupied bed.
    assert bed.assign_patient_to_bed(store, "p2", "bed1") is False
    assert store.get("er:bed:bed1")["occupied_by"] == "p1"
    assert store.get("er:bed:bed1")["status"] == "occupied"


def test_patient_not_assigned_to_two_beds():
    # @spec DOMAIN-STATE-002
    store = _store()
    assert bed.assign_patient_to_bed(store, "p1", "bed1") is True
    # The same patient cannot also take a second bed.
    assert bed.assign_patient_to_bed(store, "p1", "bed2") is False
    assert store.get("er:patient:p1")["assigned_bed"] == "bed1"
    assert store.get("er:bed:bed2")["occupied_by"] is None


def test_bed_assignment_is_idempotent():
    # @spec DOMAIN-STATE-001
    # @spec DOMAIN-STATE-002
    store = _store()
    assert bed.assign_patient_to_bed(store, "p1", "bed1") is True
    # Re-applying the identical assignment is a no-op success, not a violation.
    assert bed.assign_patient_to_bed(store, "p1", "bed1") is True
    assert store.get("er:bed:bed1")["occupied_by"] == "p1"
    assert store.get("er:patient:p1")["assigned_bed"] == "bed1"


def test_release_frees_bed_for_reassignment():
    # @spec DOMAIN-STATE-001
    store = _store()
    bed.assign_patient_to_bed(store, "p1", "bed1")
    bed.release_bed(store, "bed1")
    assert store.get("er:bed:bed1")["occupied_by"] is None
    assert store.get("er:bed:bed1")["status"] == "available"
    # Once freed, another patient may occupy it.
    assert bed.assign_patient_to_bed(store, "p2", "bed1") is True


def test_discharged_patient_not_triaged_without_new_intake():
    # @spec DOMAIN-STATE-003
    store = _store()
    store.set("er:patient:p1", {"id": "p1", "status": "discharged"})
    assert patient.can_triage(store, "p1") is False
    # A waiting (freshly intaken) patient may be triaged.
    store.set("er:patient:p2", {"id": "p2", "status": "waiting"})
    assert patient.can_triage(store, "p2") is True
