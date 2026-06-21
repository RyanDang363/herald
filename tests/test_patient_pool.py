"""Phase 2 — PatientAgent pool binding (INTAKE-BIND-002/003).

Unit tests over the pure pool helpers against an InMemoryStore (no live Bureau). The pool is a fixed
set of pre-instantiated idle PatientAgents; intake binds the next idle one and hydrates it with the
patient record. When none are idle, binding fails — the signal the Orchestrator turns into the
"patient capacity reached" path (INTAKE-BIND-003, Orchestrator side lands in Phase 3).
"""

from er_twin.agents import patient
from er_twin.storage import InMemoryStore


def _record(pid: str) -> dict:
    return {
        "id": pid,
        "name": "Jordan Lee",
        "chief_complaint": "chest pain",
        "status": "waiting",
        "vitals": {"hr": 102, "spo2": 94},
    }


def test_bind_idle_slot_hydrates_record():
    # @spec INTAKE-BIND-002
    store = InMemoryStore()
    patient.init_state(store)

    slot = patient.find_idle_slot(store)
    assert slot is not None

    rec = _record("p1")
    assert patient.bind_slot(store, slot, "p1", rec) is True
    # bound_to is set on the pool agent...
    assert store.get(patient.slot_key(slot))["bound_to"] == "p1"
    # ...and the clinical record is hydrated into er:patient:p1.
    assert store.get("er:patient:p1") == rec


def test_bind_is_idempotent_for_same_patient():
    # @spec INTAKE-BIND-002
    store = InMemoryStore()
    patient.init_state(store)
    slot = patient.find_idle_slot(store)
    patient.bind_slot(store, slot, "p1", _record("p1"))

    # Re-binding the same patient to the same slot is a no-op success (not a second binding).
    assert patient.bind_slot(store, slot, "p1", _record("p1")) is True
    assert store.get(patient.slot_key(slot))["bound_to"] == "p1"
    # Only this slot is bound; the rest of the pool stays idle.
    bound = [s for s in range(1, patient.PATIENT_COUNT + 1) if store.get(patient.slot_key(s))["bound_to"]]
    assert bound == [slot]


def test_pool_exhaustion_reports_no_idle_slot():
    # @spec INTAKE-BIND-003
    store = InMemoryStore()
    patient.init_state(store)

    # Bind every slot in the pool.
    for i in range(1, patient.PATIENT_COUNT + 1):
        slot = patient.find_idle_slot(store)
        assert slot is not None
        assert patient.bind_slot(store, slot, f"p{i}", _record(f"p{i}")) is True

    # No idle PatientAgent remains -> capacity reached.
    assert patient.find_idle_slot(store) is None


def test_bind_rejects_slot_held_by_another_patient():
    # @spec INTAKE-BIND-003
    store = InMemoryStore()
    patient.init_state(store)
    patient.bind_slot(store, 1, "p1", _record("p1"))

    # Slot 1 already owns p1; it must not be reassigned to a different patient.
    assert patient.bind_slot(store, 1, "p2", _record("p2")) is False
    assert store.get(patient.slot_key(1))["bound_to"] == "p1"
