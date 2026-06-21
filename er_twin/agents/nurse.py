"""NurseAgent pool (LLD §2 Nurse).

One agent per nurse; state lives in `er:nurse:{id}` (`available`, `location`, `assignments`). Phase 2
seeded the roster + availability helpers; Phase 3 added intake assignment (in-process). Phase 4 adds
the Event-2 oxygen path: a `StaffDispatchRequest` handler (real async messaging) and `dispatch_nurse`,
the pure mutation the Orchestrator applies on an accepted dispatch (decision R2-C).
"""

from uagents import Agent, Context

from er_twin.addresses import seed_for
from er_twin.protocols import StaffDispatchRequest, StaffDispatchResponse
from er_twin.storage import StorageInterface

NURSES: list[str] = ["nurse1", "nurse2"]
NURSE_CAPACITY = 1  # a nurse goes unavailable after one active assignment (decision R2-A)


def nurse_key(nurse_id: str) -> str:
    return f"er:nurse:{nurse_id}"


def init_state(store: StorageInterface) -> None:
    """Seed all nurses as available with no assignments."""
    for nurse_id in NURSES:
        store.set(
            nurse_key(nurse_id),
            {"id": nurse_id, "available": True, "location": "triage", "assignments": []},
        )


def find_available_nurse(store: StorageInterface) -> str | None:
    """Return the first available nurse id, or None if all are busy."""
    for nurse_id in NURSES:
        if store.get(nurse_key(nurse_id)).get("available"):
            return nurse_id
    return None


def assign_nurse(store: StorageInterface, nurse_id: str, patient_id: str, bed_id: str | None = None) -> bool:
    """Assign a nurse to a patient; the nurse goes unavailable (single-patient capacity).

    @spec INTAKE-FLOW-008 — set unavailable, add the patient to assignments, return accepted.
    @spec INTAKE-IDEM-002 — already assigned to this patient: return True, write nothing new.
    """
    rec = store.get(nurse_key(nurse_id))
    if not rec:
        return False
    assignments = rec.get("assignments", [])
    if patient_id in assignments:
        return True
    if not rec.get("available"):
        return False
    updates: dict = {"available": False, "assignments": assignments + [patient_id]}
    if bed_id:
        updates["location"] = bed_id
    store.update(nurse_key(nurse_id), updates)
    return True


def dispatch_nurse(store: StorageInterface, nurse_id: str, bed_id: str) -> bool:
    """Move a dispatched nurse to the target bed and mark unavailable (oxygen swap, decision R2-C).

    @spec OXY-FLOW-005 — set unavailable, relocate to the bed, record the dispatch task.
    Idempotent: re-dispatching the same nurse to the same bed writes nothing new.
    """
    rec = store.get(nurse_key(nurse_id))
    if not rec:
        return False
    assignments = rec.get("assignments", [])
    task = f"oxygen_dispatch:{bed_id}"
    if task in assignments:
        return True
    store.update(
        nurse_key(nurse_id),
        {"available": False, "location": bed_id,
         "assignments": assignments + [task]},
    )
    return True


def release_nurse(store: StorageInterface, nurse_id: str, patient_id: str) -> None:
    """Release a nurse from a patient assignment and return them to triage when free."""
    rec = store.get(nurse_key(nurse_id))
    if not rec:
        return
    from er_twin.agents import patient as patient_mod

    prec = store.get(patient_mod.patient_key(patient_id))
    bed_id = prec.get("assigned_bed") if prec else None
    cleaned: list[str] = []
    for a in rec.get("assignments", []):
        if a == patient_id:
            continue
        if bed_id and a == f"oxygen_dispatch:{bed_id}":
            continue
        cleaned.append(a)
    store.update(
        nurse_key(nurse_id),
        {
            "assignments": cleaned,
            "available": len(cleaned) < NURSE_CAPACITY,
            "location": "triage" if not cleaned else rec.get("location", "triage"),
        },
    )


def build_agents(store: StorageInterface) -> list[Agent]:
    """Create one NurseAgent per nurse, wired with the Event-2 `StaffDispatchRequest` handler."""
    agents: list[Agent] = []
    for nurse_id in NURSES:
        agent = Agent(name=f"er-{nurse_id}", seed=seed_for(nurse_id), network="testnet")
        agent.on_message(StaffDispatchRequest)(_make_dispatch_handler(store, nurse_id))
        agents.append(agent)
    return agents


def _make_dispatch_handler(store: StorageInterface, nurse_id: str):
    async def on_dispatch(ctx: Context, sender: str, msg: StaffDispatchRequest):
        # @spec OXY-FLOW-005 — accept if available; the Orchestrator applies the swap on the response.
        accepted = bool(store.get(nurse_key(nurse_id)).get("available"))
        ctx.logger.info(
            f"{nurse_id} {'accepts' if accepted else 'declines'} dispatch "
            f"{msg.task!r} -> {msg.target_location} ({msg.equipment_id})"
        )
        await ctx.send(
            sender,
            StaffDispatchResponse(
                staff_id=nurse_id,
                accepted=accepted,
                eta_note="en route, ~15s" if accepted else "unavailable",
                flow_id=msg.flow_id,
            ),
        )

    return on_dispatch
