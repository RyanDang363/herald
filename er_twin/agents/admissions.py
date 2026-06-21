"""AdmissionsAgent (Event 1, INTAKE-FLOW-002 / INTAKE-IDEM-001).

Creates the patient clinical record at intake: mints a deterministic id (`p{n}` via the
`er:counter:patient` counter, decision Gap 3), persists the record at `er:patient:{id}` with status
`waiting`, and dedupes — a repeat intake matching an active (non-discharged) patient by name +
chief_complaint returns the existing id without creating a second record.

Patient enumeration uses `StorageInterface.list_ids("patient")` (prefix index); that fulfils the
"er:index:patient" intent of decision Gap 3 for `InMemoryStore`, and RedisStore (Phase 6) can back
`list_ids` with a Redis set keyed `er:index:patient` without changing this module.
"""

from uagents import Agent

from er_twin.addresses import seed_for
from er_twin.storage import StorageInterface

ADMISSIONS_AGENT_ID = "admissions"
_COUNTER_KEY = "er:counter:patient"


def patient_key(patient_id: str) -> str:
    return f"er:patient:{patient_id}"


def _next_patient_id(store: StorageInterface) -> str:
    n = store.get(_COUNTER_KEY).get("value", 0) + 1
    store.set(_COUNTER_KEY, {"value": n})
    return f"p{n}"


def _find_active_duplicate(store: StorageInterface, name: str, chief_complaint: str) -> str | None:
    for pid in store.list_ids("patient"):
        rec = store.get(patient_key(pid))
        if (
            rec.get("status") != "discharged"
            and rec.get("name") == name
            and rec.get("chief_complaint") == chief_complaint
        ):
            return pid
    return None


def intake(
    store: StorageInterface, name: str, chief_complaint: str, vitals: dict
) -> tuple[str, dict, bool]:
    """Create (or dedupe) a patient record. Returns ``(patient_id, record, created)``.

    @spec INTAKE-FLOW-002 — new patient: status `waiting`, persisted, id returned.
    @spec INTAKE-IDEM-001 — active duplicate (name + chief_complaint): existing id, no new record.
    """
    existing = _find_active_duplicate(store, name, chief_complaint)
    if existing is not None:
        return existing, store.get(patient_key(existing)), False

    patient_id = _next_patient_id(store)
    record = {
        "id": patient_id,
        "name": name,
        "chief_complaint": chief_complaint,
        "vitals": dict(vitals),
        "acuity": None,
        "specialty": None,
        "status": "waiting",
        "assigned_bed": None,
        "care_team": [],
    }
    store.set(patient_key(patient_id), record)
    return patient_id, record, True


def build_agents(store: StorageInterface) -> list[Agent]:
    """The AdmissionsAgent. The `PatientIntakeRequest` handler (Phase 3 wiring) calls `intake`."""
    return [Agent(name="er-admissions", seed=seed_for(ADMISSIONS_AGENT_ID), network="testnet")]
