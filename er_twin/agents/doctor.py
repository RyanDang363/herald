"""DoctorAgent pool (LLD §2 Doctor).

One agent per doctor; state lives in `er:doctor:{id}` (`available`, `specialty`, `load`,
`assignments`). Phase 2 seeds the roster and provides a specialty-aware availability helper; the
`StaffAssignRequest` handler + load increment (INTAKE-FLOW-011) arrive in Phase 3.
"""

from uagents import Agent

from er_twin.addresses import seed_for
from er_twin.storage import StorageInterface

# Doctor id -> specialty (matches dashboard/fixtures/er_state.json).
DOCTORS: dict[str, str] = {"doc1": "cardiology", "doc2": "general"}
DOCTOR_LOAD_CAP = 3  # a doctor stays available while load < cap (decision R2-A)


def doctor_key(doctor_id: str) -> str:
    return f"er:doctor:{doctor_id}"


def init_state(store: StorageInterface) -> None:
    """Seed all doctors as available with zero load."""
    for doctor_id, specialty in DOCTORS.items():
        store.set(
            doctor_key(doctor_id),
            {
                "id": doctor_id,
                "available": True,
                "specialty": specialty,
                "load": 0,
                "assignments": [],
            },
        )


def find_available_doctor(store: StorageInterface, specialty: str | None = None) -> str | None:
    """Return an available doctor, preferring a specialty match, else any available doctor."""
    available = [d for d in DOCTORS if store.get(doctor_key(d)).get("available")]
    if specialty:
        for doctor_id in available:
            if store.get(doctor_key(doctor_id)).get("specialty") == specialty:
                return doctor_id
    return available[0] if available else None


def assign_doctor(
    store: StorageInterface, doctor_id: str, patient_id: str, bed_id: str | None = None
) -> bool:
    """Page a doctor: increment load, add the patient; goes unavailable only at the load cap.

    @spec INTAKE-FLOW-011 — increment load, add the patient to assignments, return accepted.
    @spec INTAKE-IDEM-002 — already assigned to this patient: return True, write nothing new.
    """
    rec = store.get(doctor_key(doctor_id))
    if not rec:
        return False
    assignments = rec.get("assignments", [])
    if patient_id in assignments:
        return True
    if rec.get("load", 0) >= DOCTOR_LOAD_CAP:
        return False
    load = rec.get("load", 0) + 1
    updates: dict = {
        "load": load,
        "assignments": assignments + [patient_id],
        "available": load < DOCTOR_LOAD_CAP,
    }
    if bed_id:
        updates["location"] = bed_id
    store.update(doctor_key(doctor_id), updates)
    return True


def release_doctor(store: StorageInterface, doctor_id: str, patient_id: str) -> None:
    """Remove a patient from a doctor's assignments and decrement load."""
    rec = store.get(doctor_key(doctor_id))
    if not rec:
        return
    assignments = [a for a in rec.get("assignments", []) if a != patient_id]
    load = max(0, rec.get("load", 0) - (1 if patient_id in rec.get("assignments", []) else 0))
    store.update(
        doctor_key(doctor_id),
        {
            "assignments": assignments,
            "load": load,
            "available": load < DOCTOR_LOAD_CAP,
            "location": "triage" if not assignments else rec.get("location", "triage"),
        },
    )


def build_agents(store: StorageInterface) -> list[Agent]:
    """Create one DoctorAgent per doctor, wired with intake and release handlers.

    Handlers wired:
    - StaffAssignRequest  → Event 1 (intake doctor paging)
    - StaffReleaseRequest → Event 4 (resolve: release doctor from discharged patient)
    """
    from uagents import Context

    from er_twin.addresses import ORCHESTRATOR_ADDRESS
    from er_twin.protocols import StaffAssignRequest, StaffAssignResponse, StaffReleaseRequest, StaffReleaseResponse

    agents: list[Agent] = []
    for doctor_id in DOCTORS:
        agent = Agent(name=f"er-{doctor_id}", seed=seed_for(doctor_id), network="testnet")

        def _make_handlers(this_doctor_id: str):
            async def on_assign(ctx: Context, sender: str, msg: StaffAssignRequest) -> None:
                if msg.role != "doctor":
                    return  # nurse assign messages are not for a doctor agent
                accepted = assign_doctor(store, this_doctor_id, msg.patient_id, bed_id=msg.bed_id)
                ctx.logger.info(
                    f"{this_doctor_id} {'accepted' if accepted else 'declined'} page "
                    f"for {msg.patient_id} at {msg.bed_id}"
                )
                await ctx.send(
                    ORCHESTRATOR_ADDRESS,
                    StaffAssignResponse(
                        patient_id=msg.patient_id,
                        staff_id=this_doctor_id,
                        accepted=accepted,
                        role="doctor",
                        flow_id=msg.flow_id,
                    ),
                )

            async def on_release(ctx: Context, sender: str, msg: StaffReleaseRequest) -> None:
                if msg.role != "doctor":
                    return
                release_doctor(store, this_doctor_id, msg.patient_id)
                ctx.logger.info(
                    f"{this_doctor_id}: released from patient {msg.patient_id} (resolve flow)"
                )
                await ctx.send(
                    ORCHESTRATOR_ADDRESS,
                    StaffReleaseResponse(
                        patient_id=msg.patient_id,
                        staff_id=this_doctor_id,
                        role="doctor",
                        released=True,
                        flow_id=msg.flow_id,
                    ),
                )

            return on_assign, on_release

        on_assign, on_release = _make_handlers(doctor_id)
        agent.on_message(StaffAssignRequest)(on_assign)
        agent.on_message(StaffReleaseRequest)(on_release)
        agents.append(agent)
    return agents
