"""PatientAgent pool (LLD §2 Patient Agent Pool).

A fixed set of PatientAgents is pre-instantiated at Bureau startup as an idle pool — never spawned at
runtime, to keep addressing deterministic and the demo stable. On intake the Orchestrator binds an
incoming patient to the next idle agent (`bind_slot`) and hydrates it with the clinical record; the
bound agent then "owns" that patient (and can autonomously deteriorate in Event 2). Pool occupancy
lives in the shared store under `er:patientagent:{slot}` (`bound_to` = the owned patient id or None);
the patient's clinical record lives in `er:patient:{id}` (LLD §2 / §4).

The pure helpers (`init_state`, `find_idle_slot`, `bind_slot`, `can_triage`) carry the logic so the
binding (INTAKE-BIND-002/003) and discharge invariant (DOMAIN-STATE-003) are unit-testable without a
live Bureau. `build_agents` wraps them as real uAgents whose `PatientBindRequest` handler binds the
agent's own slot.
"""

from uagents import Agent, Context

from er_twin.addresses import seed_for
from er_twin.protocols import PatientBindRequest, PatientBindResponse
from er_twin.storage import StorageInterface

PATIENT_COUNT = 3


def slot_key(slot: int) -> str:
    return f"er:patientagent:{slot}"


def patient_key(patient_id: str) -> str:
    return f"er:patient:{patient_id}"


def agent_id_for(slot: int) -> str:
    return f"patient-{slot}"


def init_state(store: StorageInterface) -> None:
    """Seed the idle pool — every PatientAgent starts unbound."""
    for slot in range(1, PATIENT_COUNT + 1):
        store.set(slot_key(slot), {"slot": slot, "bound_to": None})


def find_idle_slot(store: StorageInterface) -> int | None:
    """Return the lowest idle pool slot, or None when the pool is exhausted.

    @spec INTAKE-BIND-003 — pool-exhaustion detection; the None case is what the Orchestrator turns
    into the "patient capacity reached" chat report (Orchestrator side lands in Phase 3).
    """
    for slot in range(1, PATIENT_COUNT + 1):
        if store.get(slot_key(slot)).get("bound_to") is None:
            return slot
    return None


def bind_slot(store: StorageInterface, slot: int, patient_id: str, record: dict) -> bool:
    """Bind `patient_id` to pool `slot` and hydrate its record (INTAKE-BIND-002).

    Idempotent: re-binding the same patient to the same slot succeeds without a second binding.
    A slot already owned by a *different* patient is refused (returns False).
    """
    bound_to = store.get(slot_key(slot)).get("bound_to")
    if bound_to not in (None, patient_id):
        return False
    store.update(slot_key(slot), {"bound_to": patient_id})
    store.set(patient_key(patient_id), record)
    return True


def can_triage(store: StorageInterface, patient_id: str) -> bool:
    # @spec DOMAIN-STATE-003 — a discharged patient may not be triaged without a fresh intake.
    return store.get(patient_key(patient_id)).get("status") != "discharged"


def release_slot(store: StorageInterface, patient_id: str) -> None:
    """Free the pool slot bound to `patient_id` so a later intake can reuse it.

    Without this, every discharge leaks one of the fixed `PATIENT_COUNT` slots; after a few
    discharge→re-admit cycles `find_idle_slot` returns None and intake reports "patient capacity
    reached" even though the ER is empty. Idempotent: a no-op when no slot owns the patient.
    """
    for slot in range(1, PATIENT_COUNT + 1):
        if store.get(slot_key(slot)).get("bound_to") == patient_id:
            store.update(slot_key(slot), {"bound_to": None})


def build_agents(store: StorageInterface) -> list[Agent]:
    """Create the pool of PatientAgents, each bound to one slot of the shared store."""
    agents: list[Agent] = []
    for slot in range(1, PATIENT_COUNT + 1):
        agent = Agent(name=f"er-patient-{slot}", seed=seed_for(agent_id_for(slot)), network="testnet")

        def _make_handler(slot_index: int):
            async def on_bind(ctx: Context, sender: str, msg: PatientBindRequest):
                # @spec INTAKE-BIND-002 — bind this agent's slot and hydrate the record, then reply.
                bound = bind_slot(store, slot_index, msg.patient_id, msg.record)
                if bound:
                    ctx.logger.info(f"bound patient {msg.patient_id} to {agent_id_for(slot_index)}")
                else:
                    ctx.logger.warning(f"{agent_id_for(slot_index)} busy; cannot bind {msg.patient_id}")
                await ctx.send(
                    sender,
                    PatientBindResponse(
                        patient_id=msg.patient_id,
                        agent_id=agent_id_for(slot_index),
                        bound=bound,
                    ),
                )

            return on_bind

        agent.on_message(PatientBindRequest)(_make_handler(slot))
        agents.append(agent)
    return agents
