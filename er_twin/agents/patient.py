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
from er_twin.protocols import PatientBindRequest, PatientBindResponse, PatientDischargeRequest, PatientDischargeResponse
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


def find_patient_slot(store: StorageInterface, patient_id: str) -> int | None:
    """Return the pool slot currently bound to patient_id, or None if not found."""
    for slot in range(1, PATIENT_COUNT + 1):
        if store.get(slot_key(slot)).get("bound_to") == patient_id:
            return slot
    return None


def can_triage(store: StorageInterface, patient_id: str) -> bool:
    # @spec DOMAIN-STATE-003 — a discharged patient may not be triaged without a fresh intake.
    return store.get(patient_key(patient_id)).get("status") != "discharged"


def build_agents(store: StorageInterface) -> list[Agent]:
    """Create the pool of PatientAgents, each bound to one slot of the shared store."""
    agents: list[Agent] = []
    for slot in range(1, PATIENT_COUNT + 1):
        agent = Agent(
            name=f"er-patient-{slot}", seed=seed_for(agent_id_for(slot)), network="testnet"
        )

        def _make_handlers(slot_index: int):
            async def on_bind(ctx: Context, sender: str, msg: PatientBindRequest):
                # @spec INTAKE-BIND-002 — bind this agent's slot and hydrate the record, then reply.
                bound = bind_slot(store, slot_index, msg.patient_id, msg.record)
                if bound:
                    ctx.logger.info(f"bound patient {msg.patient_id} to {agent_id_for(slot_index)}")
                else:
                    ctx.logger.warning(
                        f"{agent_id_for(slot_index)} busy; cannot bind {msg.patient_id}"
                    )
                await ctx.send(
                    sender,
                    PatientBindResponse(
                        patient_id=msg.patient_id,
                        agent_id=agent_id_for(slot_index),
                        bound=bound,
                        flow_id=msg.flow_id,
                    ),
                )

            async def on_discharge(ctx: Context, sender: str, msg: PatientDischargeRequest):
                """Mark the bound patient discharged and record sign-off staff."""
                rec = store.get(patient_key(msg.patient_id))
                if not rec or rec.get("status") == "discharged":
                    await ctx.send(
                        sender,
                        PatientDischargeResponse(
                            patient_id=msg.patient_id, confirmed=False, flow_id=msg.flow_id
                        ),
                    )
                    return
                store.update(patient_key(msg.patient_id), {"status": "discharged"})
                signoff = [sid for sid in (msg.nurse_id, msg.doctor_id) if sid]
                store.update(patient_key(msg.patient_id), {"discharge_signed_by": signoff})
                # Release the slot so it can be reused for the next intake.
                store.update(slot_key(slot_index), {"bound_to": None})

                from er_twin.display import display as _display

                name = rec.get("name", msg.patient_id)
                mrn = rec.get("mrn", "")
                bed_id = rec.get("assigned_bed")
                team_text = (
                    " + ".join(_display(sid) for sid in signoff) if signoff else "no staff sign-off"
                )
                bed_text = _display(bed_id) if bed_id else "waiting area"
                confirmation = (
                    f"Discharge confirmed for {name} ({mrn}) from {bed_text}. "
                    f"Signed off by {team_text}. Resolve to free bed and staff."
                )
                ctx.logger.info(f"discharged patient {msg.patient_id} from slot {slot_index}")
                await ctx.send(
                    sender,
                    PatientDischargeResponse(
                        patient_id=msg.patient_id,
                        confirmed=True,
                        confirmation=confirmation,
                        flow_id=msg.flow_id,
                    ),
                )

            return on_bind, on_discharge

        on_bind, on_discharge = _make_handlers(slot)
        agent.on_message(PatientBindRequest)(on_bind)
        agent.on_message(PatientDischargeRequest)(on_discharge)
        agents.append(agent)
    return agents
