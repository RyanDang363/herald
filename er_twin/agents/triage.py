"""TriageAgent (Event 1, INTAKE-FLOW-004 / INTAKE-STATE-002 / DOMAIN-STATE-003).

Assigns an ESI acuity (1 most urgent … 5 least) AND a required care specialty from the chief
complaint (decision Gap 1), and persists both to the patient record. Under USE_MOCK / the deterministic
demo, the mapping is a hardcoded complaint table (vitals are carried but not scored). A discharged
patient may not be triaged without a fresh intake (DOMAIN-STATE-003).
"""

from uagents import Agent

from er_twin.addresses import seed_for
from er_twin.agents import patient
from er_twin.storage import StorageInterface

TRIAGE_AGENT_ID = "triage"

# chief_complaint substring -> (acuity 1..5, specialty). First match wins; default last.
_COMPLAINT_TABLE: tuple[tuple[str, int, str], ...] = (
    ("chest pain", 2, "cardiology"),
    ("shortness of breath", 3, "general"),
    ("oxygen", 3, "general"),
)
_DEFAULT_ACUITY, _DEFAULT_SPECIALTY = 3, "general"


def assess(chief_complaint: str, vitals: dict | None = None) -> tuple[int, str]:
    """Pure deterministic triage: map a chief complaint to (acuity, specialty)."""
    text = (chief_complaint or "").lower()
    for keyword, acuity, specialty in _COMPLAINT_TABLE:
        if keyword in text:
            return acuity, specialty
    return _DEFAULT_ACUITY, _DEFAULT_SPECIALTY


def triage(store: StorageInterface, patient_id: str) -> tuple[int, str]:
    """Assess and persist acuity + specialty on the patient record. Returns ``(acuity, specialty)``.

    @spec INTAKE-FLOW-004 — assign acuity (1–5) and specialty, persist to the record.
    @spec DOMAIN-STATE-003 — refuse to triage a discharged patient (raises ValueError).
    """
    if not patient.can_triage(store, patient_id):
        raise ValueError(f"cannot triage discharged patient {patient_id} without a new intake")
    record = store.get(patient.patient_key(patient_id))
    acuity, specialty = assess(record.get("chief_complaint", ""), record.get("vitals"))
    store.update(patient.patient_key(patient_id), {"acuity": acuity, "specialty": specialty})
    return acuity, specialty


def build_agents(store: StorageInterface) -> list[Agent]:
    """Create the TriageAgent, wired with the TriageRequest handler.

    @spec INTAKE-FLOW-004 — on TriageRequest: run assess+persist and reply with TriageResponse.
    """
    from uagents import Context

    from er_twin.addresses import ORCHESTRATOR_ADDRESS
    from er_twin.protocols import TriageRequest, TriageResponse

    agent = Agent(name="er-triage", seed=seed_for(TRIAGE_AGENT_ID), network="testnet")

    @agent.on_message(TriageRequest)
    async def on_triage(ctx: Context, sender: str, msg: TriageRequest) -> None:
        try:
            acuity, specialty = triage(store, msg.patient_id)
        except ValueError as exc:
            ctx.logger.warning(f"triage refused for {msg.patient_id}: {exc}")
            # Use the pure assess() fallback so the flow doesn't stall
            acuity, specialty = assess(msg.chief_complaint)
        ctx.logger.info(f"triage: {msg.patient_id} acuity={acuity} specialty={specialty!r}")
        await ctx.send(
            ORCHESTRATOR_ADDRESS,
            TriageResponse(
                patient_id=msg.patient_id,
                acuity=acuity,
                specialty=specialty,
                flow_id=msg.flow_id,
            ),
        )

    return [agent]
