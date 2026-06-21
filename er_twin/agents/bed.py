"""BedAgent pool (LLD §2 Bed).

One agent per physical bed; bed state lives in `er:bed:{id}`. Phase 2 establishes the beds, their
specialties, and the occupancy invariants. The `BedAssignRequest` flow (specialty matching, general
fallback, idempotency — INTAKE-FLOW/ERR/IDEM) is wired in Phase 3 on top of `assign_patient_to_bed`.

`assign_patient_to_bed` is the guarded mutation that enforces both bed-side invariants:
- DOMAIN-STATE-001: a bed holds at most one patient.
- DOMAIN-STATE-002: a patient holds at most one bed.
It is idempotent (re-applying the same assignment succeeds and writes nothing new) and returns False
on a violation rather than raising.
"""

from uagents import Agent

from er_twin.addresses import seed_for
from er_twin.storage import StorageInterface

# Demo bed inventory (ids/specialties match the shared fixture in docs/TEAM.md).
BEDS: dict[str, str] = {
    "bed1": "cardiology",
    "bed2": "general",
    "bed3": "general",
    "bed4": "trauma",
}


def bed_key(bed_id: str) -> str:
    return f"er:bed:{bed_id}"


def patient_key(patient_id: str) -> str:
    return f"er:patient:{patient_id}"


def init_state(store: StorageInterface) -> None:
    """Seed all beds as available and empty."""
    for bed_id, specialty in BEDS.items():
        store.set(
            bed_key(bed_id),
            {
                "id": bed_id,
                "occupied_by": None,
                "status": "available",
                "specialty": specialty,
                "equipment": [],
            },
        )


def assign_patient_to_bed(store: StorageInterface, patient_id: str, bed_id: str) -> bool:
    """Occupy `bed_id` with `patient_id`, enforcing DOMAIN-STATE-001 and DOMAIN-STATE-002.

    Returns False (no state change) if the bed is held by another patient, if the patient already
    holds a different bed, or if the bed does not exist. Idempotent for the same (patient, bed) pair.
    """
    bed = store.get(bed_key(bed_id))
    if not bed:
        return False

    # @spec DOMAIN-STATE-001 — bed must be free or already this patient's.
    if bed.get("occupied_by") not in (None, patient_id):
        return False

    # @spec DOMAIN-STATE-002 — patient must not already hold a different bed.
    if store.get(patient_key(patient_id)).get("assigned_bed") not in (None, bed_id):
        return False

    store.update(bed_key(bed_id), {"occupied_by": patient_id, "status": "occupied"})
    store.update(patient_key(patient_id), {"assigned_bed": bed_id})
    return True


def find_available_bed(store: StorageInterface, required_specialty: str) -> str | None:
    """Pick an available bed for the required specialty, falling back to a `general` bed.

    @spec INTAKE-FLOW-006 — prefer a free matching-specialty bed.
    @spec INTAKE-ERR-001 — fall back to a free `general` bed when no specialty match is free.
    @spec INTAKE-ERR-002 — return None when no bed is free at all (caller leaves the patient waiting).
    """
    # A bed is selectable only if its record actually exists and is free — a missing/empty hash
    # (e.g. an un-seeded backend) must NOT be treated as an available bed (it has no specialty and
    # would never match anyway, but counting it as "free" masks the real "inventory missing" problem).
    records = {bid: store.get(bed_key(bid)) for bid in BEDS}
    free = [bid for bid, rec in records.items() if rec and rec.get("occupied_by") is None]
    for bid in free:
        if records[bid].get("specialty") == required_specialty:
            return bid
    for bid in free:
        if records[bid].get("specialty") == "general":
            return bid
    return None


def release_bed(store: StorageInterface, bed_id: str) -> None:
    """Free a bed and detach its patient's bed link, returning it to the available pool."""
    bed = store.get(bed_key(bed_id))
    if not bed:
        return
    occupant = bed.get("occupied_by")
    store.update(bed_key(bed_id), {"occupied_by": None, "status": "available"})
    if occupant:
        store.update(patient_key(occupant), {"assigned_bed": None})


def build_agents(store: StorageInterface) -> list[Agent]:
    """Create one BedAgent per bed. Assignment handlers are added in Phase 3."""
    return [
        Agent(name=f"er-{bed_id}", seed=seed_for(bed_id), network="testnet") for bed_id in BEDS
    ]
