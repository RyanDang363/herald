"""OrchestratorAgent — the single public, ASI:One-reachable surface of the ER Twin.

This is the only agent with a mailbox + Chat Protocol (ORCH-CHAT-001); every other agent is a
private Bureau member. The Orchestrator turns inbound chat text into a structured intent — via the
ASI:One LLM, or a hardcoded `USE_MOCK` lookup (ORCH-LLM-003) — and fans out to the entity agents.

Phase 1 (this file) implements the skeleton loop only:

    chat "ping" → resolve intent → dispatch PingRequest to the stub IN-PROCESS → on PingResponse,
    relay the stub's text back to the chat user.

The non-skeleton intents now drive their real flows: intake (`run_intake`, in-process) and oxygen
(real async messaging) in Phases 3–4, and the read-only status summary (`build_status_summary`) in
Phase 5. `MOCK_REPLIES` survives only as the no-store fallback those branches reference. Unknown text
yields a clarifying message and dispatches nothing (ORCH-LLM-004).

**Async, not request/response (LLD §5).** uAgent sends are fire-and-forget — the stub's reply lands
in a *separate* `@on_message(PingResponse)` handler, not inline in the chat handler. The chat handler
records the chat sender; the response handler looks it up and replies. uAgents does not carry the
chat session across the Orchestrator→stub→Orchestrator hop (that hop is its own session), so the
ping bridge also keeps a small FIFO of pending chat sessions — correct because commands are
serialized one-at-a-time (ORCH-SYS-003).
"""

import asyncio
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    TextContent,
    chat_protocol_spec,
)

from er_twin import replay
from er_twin.addresses import STUB_ADDRESS, address_for, seed_for
from er_twin.agents import admissions, bed, doctor, equipment, nurse, patient, triage
from er_twin.config import settings
from er_twin.protocols import (
    EquipmentLocateRequest,
    EquipmentLocateResponse,
    LowSupplyAlert,
    PingRequest,
    PingResponse,
    SimulateOxygenDropRequest,
    StaffDispatchRequest,
    StaffDispatchResponse,
)
from er_twin.storage import StorageInterface

ORCHESTRATOR_AGENT_ID = "orchestrator"

# --- Intent resolution (USE_MOCK hardcoded lookup, ORCH-LLM-003) ---

# Each intent maps to the substrings that identify it in inbound chat text. Phrases come from the
# shared USE_MOCK contract in docs/TEAM.md — keep them in sync.
# Order matters: more specific event phrases are matched before the bare "ping" token (so e.g.
# "dropping" never trips the ping path). Matching is whole-word (word-boundary) — see resolve_intent.
_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "intake": ("chest pain", "new patient arrived"),
    "oxygen": ("oxygen is dropping", "oxygen"),
    "summary": ("what's happening in the er", "show me what", "status summary"),
    "ping": ("ping",),
}

# No-store fallback replies, referenced by the intake/oxygen/summary branches only when no shared store
# is wired (never in normal operation — main.py always injects one). The real replies are now state-
# derived; the summary string here is illustrative-only (decision R2-F) and never the shipped answer.
# `ping` is intentionally absent: it always round-trips through the stub (ORCH-SKEL-001), so its
# reply is the stub's live PingResponse text, never a canned string.
MOCK_REPLIES: dict[str, str] = {
    "intake": (
        "Admitted Jordan Lee (chest pain). Triage ESI-2. "
        "Assigned bed-1 + nurse-1; paged Dr. Smith (cardiology)."
    ),
    "oxygen": "Low O2 on bed-3 (88%). Dispatched nurse-2 with replacement unit o2-2. ETA ~15s.",
    "summary": "3 patients active, 2 beds occupied, 1 nurse free. No critical alerts.",
}

CLARIFICATION = (
    "I'm not sure what you'd like me to do. Try: 'A new patient arrived with chest pain', "
    "'Bed 3's patient oxygen is dropping', or 'Show me what's happening in the ER'."
)

# USE_MOCK intake payloads keyed by trigger phrase (decision Gap 2) — the chat text only carries the
# complaint, so name + vitals come from here.
MOCK_INTAKE: dict[str, dict] = {
    "A new patient arrived with chest pain": {
        "name": "Jordan Lee",
        "chief_complaint": "chest pain",
        "vitals": {
            "heart_rate": 112, "blood_pressure": "156/92", "resp_rate": 22,
            "spo2": 96, "temperature_f": 98.6, "pain_score": 8,
        },
    },
}

# Presentation-only id → friendly name map for chat (decision Gap 7); ids stay in state. Newly
# admitted patients use their intake name directly.
DISPLAY_NAMES: dict[str, str] = {
    "nurse1": "Nurse Maya", "nurse2": "Nurse Chen",
    "doc1": "Dr. Smith", "doc2": "Dr. Patel",
    "bed1": "bed-1", "bed2": "bed-2", "bed3": "bed-3", "bed4": "bed-4",
    "o2_1": "oxygen unit o2-1", "o2_2": "replacement unit o2-2",
}


def display(entity_id: str | None) -> str:
    return DISPLAY_NAMES.get(entity_id, entity_id) if entity_id else ""


def resolve_intent(text: str) -> str:
    """Pure USE_MOCK lookup: map chat text to an intent key, or ``"unknown"`` (ORCH-LLM-003)."""
    lowered = text.lower()
    for intent, keywords in _INTENT_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(keyword)}\b", lowered) for keyword in keywords):
            return intent
    return "unknown"


def _resolve_via_llm(text: str) -> str:
    """Resolve an intent through the ASI:One LLM (ORCH-LLM-001).

    Deferred in P1: the USE_MOCK path is the only one wired, and the `openai`/ASI:One client is not
    added yet. This stub raises so `resolve_command` exercises the documented fallback (ORCH-LLM-002)
    whenever USE_MOCK is disabled. Phase 5 replaces the body with a real ASI:One call.
    """
    raise RuntimeError("ASI:One LLM is not configured in P1 (USE_MOCK path only)")


def resolve_command(text: str) -> str:
    """Resolve chat text to an intent, preferring the LLM but degrading gracefully.

    Where USE_MOCK is enabled, use the hardcoded lookup directly (ORCH-LLM-003). Otherwise call the
    ASI:One LLM and, if it times out / rate-limits / errors, fall back to the mock lookup rather than
    crash (ORCH-LLM-002).
    """
    if settings.use_mock:
        return resolve_intent(text)
    try:
        return _resolve_via_llm(text)
    except Exception:  # noqa: BLE001 — any LLM failure degrades to the deterministic mock path.
        return resolve_intent(text)


# --- Patient-intake coordination (Event 1, INTAKE-*) ---
#
# `run_intake` composes the entity agents' pure domain functions in INTAKE-FLOW order over the shared
# store and owns the patient status transitions (decision Gap 8). In P3 the Orchestrator drives this
# in-process (it invokes each entity's domain function directly) rather than via uAgent request/
# response envelopes; the behaviours, state outcomes, idempotency, and error paths are unit-tested.
# Converting the orchestrator↔entity hops to explicit async messages is a tracked follow-up that does
# not change this logic.


def _format_intake_confirmation(
    name: str, acuity: int, specialty: str, bed_id: str, nurse_id: str | None, doctor_id: str | None
) -> str:
    """Chat confirmation naming the patient, bed, and care team (INTAKE-FLOW-009; display names)."""
    head = f"Admitted {name}. Triage ESI-{acuity}."
    if nurse_id:
        care = f"Assigned {display(bed_id)} + {display(nurse_id)}"
    else:
        care = f"Assigned {display(bed_id)}; no staff available"
    if doctor_id:
        care += f"; paged {display(doctor_id)} ({specialty})."
    elif acuity <= 2:
        care += "; no doctor available."
    else:
        care += "."
    return f"{head} {care}"


def run_intake(store: StorageInterface, name: str, chief_complaint: str, vitals: dict) -> dict:
    """Run the full intake flow and return the outcome (+ confirmation + milestone log).

    @spec INTAKE-FLOW-001 @spec INTAKE-FLOW-002 @spec INTAKE-BIND-001 @spec INTAKE-FLOW-003
    @spec INTAKE-FLOW-004 @spec INTAKE-FLOW-005 @spec INTAKE-FLOW-006 @spec INTAKE-FLOW-007
    @spec INTAKE-FLOW-008 @spec INTAKE-FLOW-009 @spec INTAKE-FLOW-010 @spec INTAKE-FLOW-011
    @spec INTAKE-STATE-001 @spec INTAKE-BIND-003 @spec INTAKE-ERR-002 @spec INTAKE-ERR-003
    @spec INTAKE-ERR-004 @spec INTAKE-IDEM-001
    """
    milestones: list[dict] = []

    def log(action: str, target: str | None = None, **detail) -> None:
        milestones.append({"action": action, "target": target, "detail": detail})

    log("intake_received", detail=chief_complaint)
    patient_id, record, created = admissions.intake(store, name, chief_complaint, vitals)
    result: dict = {
        "patient_id": patient_id, "created": created, "error": None,
        "acuity": record.get("acuity"), "specialty": record.get("specialty"),
        "bed_id": record.get("assigned_bed"), "nurse_id": None, "doctor_id": None,
        "care_team": record.get("care_team", []), "status": record.get("status"),
        "milestones": milestones,
    }

    if not created:
        # @spec INTAKE-IDEM-001 — existing active patient; report current state, create nothing.
        log("intake_deduped", patient_id)
        result["confirmation"] = f"{name} is already in the ER ({record.get('status')})."
        return result
    log("record_created", patient_id)

    # @spec INTAKE-BIND-001/002/003 — bind an idle pooled PatientAgent.
    slot = patient.find_idle_slot(store)
    if slot is None:
        log("patient_capacity_reached", patient_id)
        result["error"] = "patient_capacity_reached"
        result["confirmation"] = (
            f"{name} is waiting — patient capacity reached (no free patient agent)."
        )
        return result  # status stays waiting; no triage (INTAKE-BIND-003)
    patient.bind_slot(store, slot, patient_id, store.get(patient.patient_key(patient_id)))
    log("patient_bound", patient_id, slot=slot)

    # status: waiting -> in_triage (decision Gap 8)
    store.update(patient.patient_key(patient_id), {"status": "in_triage"})
    acuity, specialty = triage.triage(store, patient_id)
    log("triaged", patient_id, acuity=acuity, specialty=specialty)
    result["acuity"], result["specialty"] = acuity, specialty

    # @spec INTAKE-FLOW-005/006 @spec INTAKE-ERR-001/002 — bed selection.
    bed_id = bed.find_available_bed(store, specialty)
    if bed_id is None:
        log("no_bed_available", patient_id)
        store.update(patient.patient_key(patient_id), {"status": "waiting"})
        result["error"], result["status"] = "no_bed_available", "waiting"
        result["confirmation"] = f"No bed available — {name} remains waiting (ESI-{acuity})."
        return result
    bed.assign_patient_to_bed(store, patient_id, bed_id)
    log("bed_assigned", bed_id, patient=patient_id)
    result["bed_id"] = bed_id
    # @spec INTAKE-STATE-001 — admitted to a bed (decision Gap 8 owns the transition).
    store.update(patient.patient_key(patient_id), {"status": "admitted"})
    result["status"] = "admitted"

    # @spec INTAKE-FLOW-007/008 @spec INTAKE-ERR-003 — nurse.
    nurse_id = nurse.find_available_nurse(store)
    if nurse_id and nurse.assign_nurse(store, nurse_id, patient_id):
        log("nurse_assigned", nurse_id, patient=patient_id)
        result["nurse_id"] = nurse_id
    else:
        log("no_nurse_available", patient_id)

    # @spec INTAKE-FLOW-010/011 @spec INTAKE-ERR-004 — page a doctor when acuity is urgent (<= 2).
    if acuity <= 2:
        candidate = doctor.find_available_doctor(store, specialty)
        if candidate and doctor.assign_doctor(store, candidate, patient_id):
            log("doctor_paged", candidate, patient=patient_id)
            result["doctor_id"] = candidate
        else:
            log("no_doctor_available", patient_id)

    team = [sid for sid in (result["nurse_id"], result["doctor_id"]) if sid]
    store.update(patient.patient_key(patient_id), {"care_team": team})
    result["care_team"] = team
    log("intake_complete", patient_id)
    result["confirmation"] = _format_intake_confirmation(
        name, acuity, specialty, bed_id, result["nurse_id"], result["doctor_id"]
    )
    return result


# --- Low-oxygen coordination (Event 2, OXY-*) ---
#
# Unlike intake, Event 2 is realized as REAL async uAgent messaging (the mandatory Fetch.ai showcase —
# decision 2026-06-20-intake-orchestration-mode): the EquipmentAgent autonomously emits `LowSupplyAlert`
# and the Orchestrator handles alert → locate → dispatch → swap across separate `@on_message` handlers
# (below), correlating the multi-hop flow by a `flow_id` threaded through every oxygen message and keyed
# in `oxygen_flows` (so overlapping/autonomous alerts never clobber each other and late/duplicate
# responses are no-ops — LLD §6). The functions here are the pure logic those handlers call; they
# unit-test against an `InMemoryStore`.


def should_start_o2_dispatch(in_flight: dict[str, str], equipment_id: str) -> bool:
    """True unless a dispatch is already in flight for this unit (decision R2-D).

    @spec OXY-IDEM-001 — a `LowSupplyAlert` for an equipment id already mid-dispatch is ignored.
    """
    return equipment_id not in in_flight


def apply_oxygen_swap(
    store: StorageInterface, depleted_id: str, replacement_id: str, bed_id: str, nurse_id: str
) -> str | None:
    """Apply the full cross-entity oxygen swap on an accepted dispatch (decision R2-C).

    @spec OXY-FLOW-005 — composes the equipment/bed/patient swap (`equipment.swap_oxygen_unit`) with
    the nurse move (`nurse.dispatch_nurse`). Returns the affected patient id.
    """
    occupant = equipment.swap_oxygen_unit(store, depleted_id, replacement_id, bed_id)
    nurse.dispatch_nurse(store, nurse_id, bed_id)
    return occupant


def format_oxygen_confirmation(bed_id: str, replacement_id: str, nurse_id: str) -> str:
    """Chat confirmation naming the bed, replacement unit, and dispatched nurse (OXY-FLOW-006)."""
    return (
        f"Low O2 on {display(bed_id)} resolved: dispatched {display(nurse_id)} with "
        f"{display(replacement_id)}; patient SpO2 restored to 96%."
    )


def _bed_from_text(text: str) -> str:
    """Resolve the target bed from the chat trigger; defaults to bed-3 for the scripted demo."""
    match = re.search(r"bed\s*(\d+)", text.lower())
    return f"bed{match.group(1)}" if match else "bed3"


# --- Status summary (Event 3, SUMM-*) ---
#
# Read-only and synchronous (LLD §7 / decision R2-F): unlike the other two events, the summary does NOT
# message any agent and does NOT mutate state — the Orchestrator reads the shared store directly and
# renders a deterministic, state-derived template. Real ASI:One synthesis is the optional LLM path
# (gated like intent resolution, SUMM-FLOW-002); USE_MOCK uses this template. `build_status_summary`
# is a pure function over a `StorageInterface`, unit-tested directly; the chat branch is a thin wrapper.

# Patient statuses that count as "active" in the summary (everything but discharged — decision R2-F).
_ACTIVE_PATIENT_STATUSES = {"waiting", "in_triage", "admitted", "in_treatment"}


def _plural(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural


def _active_patients(store: StorageInterface) -> list[dict]:
    """Patient records in a non-discharged (active) status (SUMM-FLOW-001)."""
    records = [store.get(patient.patient_key(pid)) for pid in store.list_ids("patient")]
    return [r for r in records if r.get("status") in _ACTIVE_PATIENT_STATUSES]


def build_status_summary(store: StorageInterface, active_o2_alert_beds: list[str]) -> str:
    """Render the deterministic, store-derived ER status summary (decision R2-F).

    Pure + read-only (SUMM-STATE-001): reads patients/beds/nurses via the store and returns a string,
    never mutating state. `active_o2_alert_beds` is the list of beds with an in-flight oxygen dispatch,
    computed by the caller from `oxygen_flows`/`in_flight_o2_dispatches` (see the summary chat branch),
    so this stays a pure function the unit tests exercise by injecting a list.

    @spec SUMM-FLOW-001 @spec SUMM-FLOW-002 @spec SUMM-ERR-001 @spec SUMM-STATE-001
    """
    active = _active_patients(store)
    occupied_beds = [
        bid for bid in store.list_ids("bed")
        if store.get(bed.bed_key(bid)).get("status") == "occupied"
    ]
    free_nurses = sum(
        1 for nid in store.list_ids("nurse")
        if store.get(nurse.nurse_key(nid)).get("available") is True
    )

    # @spec SUMM-ERR-001 — quiet ER: report calm, not an error.
    if not active and not occupied_beds:
        return (
            "Nothing currently happening in the ER — no active patients, "
            "no occupied beds, and no critical alerts."
        )

    n_pat, n_bed = len(active), len(occupied_beds)
    counts = (
        f"{n_pat} {_plural(n_pat, 'patient', 'patients')} active, "
        f"{n_bed} {_plural(n_bed, 'bed', 'beds')} occupied, "
        f"{free_nurses} {_plural(free_nurses, 'nurse', 'nurse(s)')} free."
    )

    # @spec SUMM-FLOW-002 — add an alert line when O2 dispatches are in flight, and a "Most urgent"
    # line when any active patient is acuity <= 2; the "No critical alerts." all-clear shows only when
    # neither applies (reconciliation in decision R2-F).
    tail: list[str] = []
    if active_o2_alert_beds:
        n_alerts = len(active_o2_alert_beds)
        beds_named = ", ".join(display(b) for b in active_o2_alert_beds)
        tail.append(f"{n_alerts} active O2 alert{_plural(n_alerts, '', 's')} on {beds_named}.")
    urgent = [p for p in active if isinstance(p.get("acuity"), int) and p["acuity"] <= 2]
    if urgent:
        top = min(urgent, key=lambda p: (p["acuity"], p.get("id", "")))
        tail.append(f"Most urgent: {top.get('name', top.get('id'))} (ESI-{top['acuity']}).")
    if not tail:
        tail.append("No critical alerts.")

    return f"{counts} {' '.join(tail)}"


# --- Async correlation & serialization primitives ---


class SessionSenders:
    """Maps a chat session id → the user address that opened it, so a reply produced in a later
    handler can be routed back to the right user (LLD §5 async correlation)."""

    def __init__(self) -> None:
        self._by_session: dict[str, str] = {}

    def remember(self, session_id: str, sender: str) -> None:
        self._by_session[session_id] = sender

    def recall(self, session_id: str) -> str | None:
        return self._by_session.get(session_id)

    def forget(self, session_id: str) -> None:
        self._by_session.pop(session_id, None)


@dataclass
class PendingChatCommand:
    """A chat command captured for deferred processing while the gate is busy (ORCH-SYS-003)."""

    sender: str
    session_id: str
    text: str


class CommandGate:
    """Serializes chat commands across their FULL lifecycle (ORCH-SYS-003).

    One command is active from dispatch until it produces its terminal chat reply; commands arriving
    while busy are queued and run when the gate frees. This is stronger than a lock around dispatch
    alone: ping/oxygen flows complete in *later* `@on_message` handlers, so the gate is released by the
    terminal finalizer (or a watchdog timeout), not when the first `ctx.send` returns. `finish` ignores
    a stale flow id so a late watchdog cannot free a newer command.
    """

    def __init__(self) -> None:
        self._active: str | None = None
        self._queue: deque[PendingChatCommand] = deque()

    def is_busy(self) -> bool:
        return self._active is not None

    def active(self) -> str | None:
        return self._active

    def start(self, flow_id: str) -> None:
        if self._active is not None:
            raise RuntimeError(f"command {self._active} already active; cannot start {flow_id}")
        self._active = flow_id

    def finish(self, flow_id: str) -> None:
        if self._active == flow_id:
            self._active = None

    def enqueue(self, cmd: PendingChatCommand) -> None:
        self._queue.append(cmd)

    def pop_next(self) -> PendingChatCommand | None:
        if self._active is not None or not self._queue:
            return None
        return self._queue.popleft()


@dataclass
class OxygenFlow:
    """Per-flow context for the multi-hop oxygen event, keyed by `flow_id` in `oxygen_flows`.

    `chat_sender` is set when the flow was triggered by a chat command (so it occupies the command
    gate); an autonomous alert leaves it None and runs ungated. `status` advances
    started → locating → dispatching → done; a response for a flow that is gone or already `done` is a
    no-op (LLD §6)."""

    flow_id: str
    bed_id: str
    alert_equipment_id: str
    session_id: str | None = None
    chat_sender: str | None = None
    replacement_id: str | None = None
    nurse_id: str | None = None
    status: str = "started"
    # Replay milestone lines accumulated for THIS flow (published to er:events + exported on terminal).
    lines: list[dict] = field(default_factory=list)


# --- Agent + chat protocol wiring ---

orchestrator = Agent(
    name="er-orchestrator",
    seed=seed_for(ORCHESTRATOR_AGENT_ID),
    mailbox=True,
    publish_agent_details=True,
    network="testnet",
)

_session_senders = SessionSenders()
_command_gate = CommandGate()
# Stub PingResponses awaited per command. uAgents does not carry the chat session across the
# Orchestrator→stub→Orchestrator hop, so we bridge with a FIFO tagged by the command flow_id (so the
# terminal handler can release the gate); serialization keeps it shallow.
_pending_ping_sessions: list[tuple[str, str]] = []  # (flow_id, session_id)

# In-flight oxygen dispatch tracking (OXY-IDEM-001 / decision R2-D): equipment_id -> flow_id. An entry
# is added when a dispatch starts and cleared only after the swap + chat reply (clear-on-completion).
in_flight_o2_dispatches: dict[str, str] = {}
# Per-flow oxygen context keyed by flow_id (LLD §6) — overlapping/autonomous alerts never collide.
oxygen_flows: dict[str, OxygenFlow] = {}

# Monotonic per-run correlation id source (no wall-clock / randomness — deterministic demo).
_flow_counter = 0
# A command whose terminal reply never arrives must not wedge the gate; release it after this long.
COMMAND_TIMEOUT_SECONDS = 30

# Shared state store, injected by main.py so the Orchestrator and entity agents read/write one store.
_store: StorageInterface | None = None

# Incident replay recorder (Phase R): holds the per-run `seq` + incident counters, publishes milestone
# lines to `er:events`, and mints incident ids. Reset per process run (no wall-clock — LLD §9).
_replay = replay.ReplayRecorder()
# Directory the replay artifacts are written to (out/{incident_id}.json + latest brief + pika_prompt.md).
REPLAY_OUT_DIR = "out"


def set_store(store: StorageInterface) -> None:
    """Inject the shared store the Orchestrator coordinates over (called from main.py at startup)."""
    global _store
    _store = store


def _emit_replay(ctx: Context, event: str, lines: list[dict]) -> None:
    """Export an incident's replay brief from its recorded milestone lines (Phase R, REPLAY-BRIEF-001).

    Best-effort: a replay-export failure must never break the live command, so it is logged and
    swallowed. Skips entirely when no store is wired or no milestone lines were recorded
    (REPLAY-BRIEF-003 — no empty artifacts)."""
    if _store is None or not lines:
        return
    try:
        incident_id = _replay.next_incident_id(event)
        brief = replay.export_incident(
            lines, incident_id, replay.INCIDENT_TYPES[event], _store, out_dir=REPLAY_OUT_DIR
        )
        if brief is not None:
            ctx.logger.info(f"replay brief written: {incident_id} -> {REPLAY_OUT_DIR}/")
    except Exception:  # noqa: BLE001 — replay export is non-critical; never crash the command.
        ctx.logger.exception("replay export failed")


def _new_flow_id(kind: str) -> str:
    """Mint a deterministic per-run flow id (e.g. ``chat-3``) for a command or alert flow."""
    global _flow_counter
    _flow_counter += 1
    return f"{kind}-{_flow_counter}"


def _drop_pending_ping(flow_id: str) -> None:
    """Remove any pending ping entry for a flow (used on watchdog timeout), forgetting its session."""
    global _pending_ping_sessions
    kept: list[tuple[str, str]] = []
    for fid, sid in _pending_ping_sessions:
        if fid == flow_id:
            _session_senders.forget(sid)
        else:
            kept.append((fid, sid))
    _pending_ping_sessions = kept

chat = Protocol(spec=chat_protocol_spec)


async def _send_chat(ctx: Context, recipient: str, text: str, end_session: bool = True) -> None:
    """Send a chat reply to ``recipient`` (ORCH-CHAT-002).

    Terminal replies end the session; the "I'll handle that next" busy-notice passes
    ``end_session=False`` so the deferred command's real reply can still land on the same session.
    """
    content: list = [TextContent(type="text", text=text)]
    if end_session:
        content.append(EndSessionContent(type="end-session"))
    await ctx.send(
        recipient,
        ChatMessage(timestamp=datetime.now(tz=timezone.utc), msg_id=uuid4(), content=content),
    )


@chat.on_message(ChatMessage)
async def handle_chat(ctx: Context, sender: str, msg: ChatMessage):
    # @spec ORCH-CHAT-002 — always acknowledge first.
    await ctx.send(
        sender,
        ChatAcknowledgement(timestamp=datetime.now(tz=timezone.utc), acknowledged_msg_id=msg.msg_id),
    )

    text = " ".join(item.text for item in msg.content if isinstance(item, TextContent)).strip()
    session_id = str(ctx.session)
    ctx.logger.info(f"chat[{session_id[:8]}] received: {text!r}")

    cmd = PendingChatCommand(sender=sender, session_id=session_id, text=text)
    # @spec ORCH-SYS-003 — one command across its full lifecycle; defer any other until this one
    # produces its reply. Deferral = queue + run on completion (the gate frees in the terminal handler).
    if _command_gate.is_busy():
        _command_gate.enqueue(cmd)
        await _send_chat(
            ctx, sender, "I'm finishing the current ER action — I'll handle that next.",
            end_session=False,
        )
        return
    await _begin_command(ctx, cmd)


async def _begin_command(ctx: Context, cmd: PendingChatCommand) -> None:
    """Reserve the gate for a fresh flow and dispatch it; finalize now if it completed synchronously."""
    flow_id = _new_flow_id("chat")
    _command_gate.start(flow_id)
    asyncio.create_task(_watchdog(ctx, flow_id))
    try:
        completed = await _dispatch_command(ctx, cmd, flow_id)
    except Exception as exc:  # noqa: BLE001 — never let a command crash the Orchestrator.
        ctx.logger.exception("command dispatch failed")
        await _send_chat(ctx, cmd.sender, f"Sorry — I hit an error handling that: {exc}")
        completed = True
    if completed:
        await _complete_command(ctx, flow_id)


async def _dispatch_command(ctx: Context, cmd: PendingChatCommand, flow_id: str) -> bool:
    """Resolve intent and start the flow. Return True if it finished synchronously (gate frees now),
    False if it is an async flow that frees the gate later from its terminal `@on_message` handler."""
    intent = resolve_command(cmd.text)
    ctx.logger.info(f"chat[{cmd.session_id[:8]}] flow={flow_id} resolved intent={intent!r}")

    if intent == "ping":
        # @spec ORCH-SKEL-001 — dispatch in-process to the stub; reply arrives in on_pong.
        _session_senders.remember(cmd.session_id, cmd.sender)
        _pending_ping_sessions.append((flow_id, cmd.session_id))
        await ctx.send(STUB_ADDRESS, PingRequest(text=cmd.text))
        return False

    if intent == "intake":
        # @spec INTAKE-FLOW-001 — run the intake flow over the shared store, relay confirmation.
        data = MOCK_INTAKE.get(cmd.text) or {"name": "Unknown Patient", "chief_complaint": cmd.text, "vitals": {}}
        if _store is None:
            await _send_chat(ctx, cmd.sender, MOCK_REPLIES["intake"])  # no store wired; safe fallback
            return True
        outcome = run_intake(_store, data["name"], data["chief_complaint"], data["vitals"])
        ctx.logger.info(f"intake -> {outcome['patient_id']} status={outcome['status']} error={outcome['error']}")
        # @spec REPLAY-LOG-001 — publish each intake milestone to er:events, then export the brief.
        lines = [
            _replay.log(_store, "intake", replay.actor_for(m["action"]), m["action"], m["target"], **m["detail"])
            for m in outcome["milestones"]
        ]
        _emit_replay(ctx, "intake", lines)
        await _send_chat(ctx, cmd.sender, outcome["confirmation"])
        return True

    if intent == "oxygen":
        # @spec OXY-FLOW-007 — kick off the real async flow: ask the bed's oxygen unit to drop.
        # The reply arrives later via on_low_supply → on_locate → on_dispatch, not inline here.
        if _store is None:
            await _send_chat(ctx, cmd.sender, MOCK_REPLIES["oxygen"])  # no store wired; safe fallback
            return True
        bed_id = _bed_from_text(cmd.text)
        eid = equipment.oxygen_unit_at_bed(_store, bed_id)
        if eid is None:
            await _send_chat(ctx, cmd.sender, f"No oxygen unit found at {display(bed_id)}.")
            return True
        _session_senders.remember(cmd.session_id, cmd.sender)
        flow = OxygenFlow(
            flow_id=flow_id, bed_id=bed_id, alert_equipment_id=eid,
            session_id=cmd.session_id, chat_sender=cmd.sender,
        )
        oxygen_flows[flow_id] = flow
        # @spec REPLAY-LOG-001 — first oxygen milestone; the rest accrue across the async handlers.
        flow.lines.append(
            _replay.log(_store, "oxygen", "orchestrator", "oxygen_drop_simulated", eid, bed=bed_id)
        )
        await ctx.send(
            address_for(eid),
            SimulateOxygenDropRequest(flow_id=flow_id, bed_id=bed_id, equipment_id=eid),
        )
        return False

    if intent == "summary":
        # @spec SUMM-FLOW-001/002 — read-only, store-derived summary (R2-F); synchronous, no mutation.
        if _store is None:
            await _send_chat(ctx, cmd.sender, MOCK_REPLIES["summary"])  # no store wired; safe fallback
            return True
        # The in-flight O2-alert beds live on the flows keyed by equipment_id -> flow_id (post-Phase-4
        # hardening). In normal gated demo operation this is empty (the gate serializes a chat-triggered
        # dispatch ahead of the summary); a non-empty list only arises from an autonomous alert mid-flight.
        alert_beds = [
            oxygen_flows[fid].bed_id
            for fid in in_flight_o2_dispatches.values()
            if fid in oxygen_flows
        ]
        summary = build_status_summary(_store, alert_beds)
        # @spec REPLAY-LOG-001 — one `summary_generated` milestone, then export the brief.
        line = _replay.log(_store, "summary", "orchestrator", "summary_generated", None, text=summary)
        _emit_replay(ctx, "summary", [line])
        await _send_chat(ctx, cmd.sender, summary)
        return True

    # @spec ORCH-LLM-004 — unknown intent: clarify, dispatch nothing.
    await _send_chat(ctx, cmd.sender, CLARIFICATION)
    return True


async def _complete_command(ctx: Context, flow_id: str) -> None:
    """Release the gate for a finished command and start the next deferred one, if any."""
    _command_gate.finish(flow_id)
    nxt = _command_gate.pop_next()
    if nxt is not None:
        await _begin_command(ctx, nxt)


async def _watchdog(ctx: Context, flow_id: str) -> None:
    """Release the gate if a command's terminal reply never arrives, so a lost message can't wedge it."""
    await asyncio.sleep(COMMAND_TIMEOUT_SECONDS)
    if _command_gate.active() != flow_id:
        return  # already completed normally
    ctx.logger.warning(f"command {flow_id} timed out before its reply; releasing gate")
    flow = oxygen_flows.get(flow_id)
    sender = flow.chat_sender if flow else None
    if sender is None:
        for fid, sid in _pending_ping_sessions:
            if fid == flow_id:
                sender = _session_senders.recall(sid)
                break
    _cleanup_oxygen(flow_id)
    _drop_pending_ping(flow_id)
    if sender:
        await _send_chat(ctx, sender, "That ER action timed out before all agents responded. Please try again.")
    await _complete_command(ctx, flow_id)


@chat.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    # Acks could drive read receipts; nothing to do for the demo.
    pass


@orchestrator.on_message(PingResponse)
async def on_pong(ctx: Context, sender: str, msg: PingResponse):
    # @spec ORCH-SKEL-001 — relay the stub's reply back to the waiting chat user, then free the gate.
    if not _pending_ping_sessions:
        ctx.logger.warning("PingResponse received with no pending chat session; dropping")
        return
    flow_id, session_id = _pending_ping_sessions.pop(0)
    user = _session_senders.recall(session_id)
    _session_senders.forget(session_id)
    if user is not None:
        await _send_chat(ctx, user, msg.text)
    else:
        ctx.logger.warning(f"no chat sender recorded for session {session_id[:8]}; dropping")
    await _complete_command(ctx, flow_id)


def _cleanup_oxygen(flow_id: str) -> None:
    """Drop a flow's context + its in-flight + chat-session bookkeeping (idempotent)."""
    flow = oxygen_flows.pop(flow_id, None)
    if flow is not None:
        in_flight_o2_dispatches.pop(flow.alert_equipment_id, None)
        if flow.session_id:
            _session_senders.forget(flow.session_id)


async def _finish_oxygen(ctx: Context, flow_id: str, reply: str) -> None:
    """Emit the terminal oxygen reply, clean up the flow, and release the command gate if it was a
    chat-triggered (gated) flow. Autonomous-alert flows have no gate to release."""
    flow = oxygen_flows.get(flow_id)
    gated = bool(flow and flow.chat_sender)
    if flow is not None and _store is not None:
        # @spec REPLAY-LOG-001 — terminal success milestone, then export the incident's brief.
        if flow.status == "done":
            flow.lines.append(_replay.log(_store, "oxygen", "orchestrator", "oxygen_event_complete", flow.bed_id))
        _emit_replay(ctx, "oxygen", flow.lines)
    if flow and flow.chat_sender:
        await _send_chat(ctx, flow.chat_sender, reply)
    else:
        ctx.logger.info(f"oxygen (no chat session): {reply}")
    _cleanup_oxygen(flow_id)
    if gated:
        await _complete_command(ctx, flow_id)


@orchestrator.on_message(LowSupplyAlert)
async def on_low_supply(ctx: Context, sender: str, msg: LowSupplyAlert):
    # @spec OXY-FLOW-001 — the EquipmentAgent's autonomous push lands here.
    eid = msg.equipment_id
    # @spec OXY-IDEM-001 — ignore an alert for a unit already mid-dispatch (decision R2-D).
    if not should_start_o2_dispatch(in_flight_o2_dispatches, eid):
        ctx.logger.info(f"duplicate_alert_ignored: O2 dispatch already in progress for {eid}")
        return

    flow = oxygen_flows.get(msg.flow_id) if msg.flow_id else None
    if flow is None:
        # Autonomous alert (no chat trigger): mint an ungated flow and locate its bed from state.
        bed_id = equipment.bed_for_equipment(_store, eid)
        if bed_id is None:
            ctx.logger.warning(f"LowSupplyAlert for {eid} with no locatable bed; ignoring")
            return
        flow = OxygenFlow(flow_id=msg.flow_id or _new_flow_id("oxygen-auto"), bed_id=bed_id, alert_equipment_id=eid)
        oxygen_flows[flow.flow_id] = flow
    flow.alert_equipment_id = eid
    in_flight_o2_dispatches[eid] = flow.flow_id
    flow.status = "locating"
    ctx.logger.info(f"alert_raised: {eid} low ({msg.supply_level}%) at {flow.bed_id} -> locating (flow={flow.flow_id})")
    # @spec REPLAY-LOG-001 — autonomous alert milestone.
    flow.lines.append(
        _replay.log(_store, "oxygen", "equipment", "alert_raised", eid, supply_level=msg.supply_level, bed=flow.bed_id)
    )

    # @spec OXY-FLOW-002 — select a same-type replacement (decision R2-E sort).
    replacement = equipment.locate_replacement(_store, msg.type, exclude_id=eid)
    flow.replacement_id = replacement
    if replacement is None:
        # @spec OXY-ERR-001 — no qualifying unit: report and do not dispatch anything.
        flow.lines.append(_replay.log(_store, "oxygen", "equipment", "no_replacement_unit_available", eid, bed=flow.bed_id))
        await _finish_oxygen(ctx, flow.flow_id, f"Low O2 on {display(flow.bed_id)}: no available replacement unit nearby.")
        return
    await ctx.send(
        address_for(replacement),
        EquipmentLocateRequest(type=msg.type, near_location=msg.location, flow_id=flow.flow_id),
    )


@orchestrator.on_message(EquipmentLocateResponse)
async def on_locate(ctx: Context, sender: str, msg: EquipmentLocateResponse):
    # @spec OXY-FLOW-003 — the candidate unit confirmed (or declined) availability.
    flow = oxygen_flows.get(msg.flow_id)
    if flow is None or flow.status == "done":
        ctx.logger.info(f"stale/duplicate locate response ignored (flow={msg.flow_id})")
        return
    if not msg.available or msg.equipment_id is None:
        # @spec OXY-ERR-001 — candidate no longer available.
        await _finish_oxygen(ctx, flow.flow_id, f"Low O2 on {display(flow.bed_id)}: no available replacement unit nearby.")
        return
    flow.replacement_id = msg.equipment_id
    flow.status = "dispatching"
    ctx.logger.info(f"unit_located: {msg.equipment_id} at {msg.location} -> dispatching nurse (flow={flow.flow_id})")
    # @spec REPLAY-LOG-001 — replacement located.
    flow.lines.append(
        _replay.log(_store, "oxygen", "equipment", "unit_located", msg.equipment_id, location=msg.location, bed=flow.bed_id)
    )

    # @spec OXY-FLOW-004 — dispatch an available nurse to bring the unit.
    nurse_id = nurse.find_available_nurse(_store)
    if nurse_id is None:
        flow.lines.append(_replay.log(_store, "oxygen", "nurse", "no_dispatch_nurse_available", flow.bed_id))
        await _finish_oxygen(
            ctx, flow.flow_id,
            f"Replacement {display(msg.equipment_id)} located for {display(flow.bed_id)}, "
            f"but no nurse is available to dispatch.",
        )
        return
    flow.nurse_id = nurse_id
    await ctx.send(
        address_for(nurse_id),
        StaffDispatchRequest(
            task="deliver_oxygen", target_location=msg.location,
            equipment_id=msg.equipment_id, flow_id=flow.flow_id,
        ),
    )


@orchestrator.on_message(StaffDispatchResponse)
async def on_dispatch(ctx: Context, sender: str, msg: StaffDispatchResponse):
    # @spec OXY-FLOW-005 — the nurse accepted; apply the swap and confirm to chat.
    flow = oxygen_flows.get(msg.flow_id)
    if flow is None or flow.status == "done":
        ctx.logger.info(f"stale/duplicate dispatch response ignored (flow={msg.flow_id})")
        return
    nurse_id = flow.nurse_id or msg.staff_id
    if not msg.accepted:
        flow.lines.append(_replay.log(_store, "oxygen", "nurse", "no_dispatch_nurse_available", flow.bed_id, nurse=nurse_id))
        await _finish_oxygen(ctx, flow.flow_id, f"{display(nurse_id)} declined the oxygen dispatch for {display(flow.bed_id)}.")
        return
    flow.status = "done"  # mark before mutating so a duplicate response is a no-op
    # @spec REPLAY-LOG-001 — nurse accepts, then the cross-entity swap completes.
    flow.lines.append(
        _replay.log(_store, "oxygen", "nurse", "nurse_dispatched", nurse_id, bed=flow.bed_id, equipment=flow.replacement_id)
    )
    apply_oxygen_swap(_store, flow.alert_equipment_id, flow.replacement_id, flow.bed_id, nurse_id)
    flow.lines.append(
        _replay.log(_store, "oxygen", "orchestrator", "oxygen_swap_complete", flow.bed_id,
                    depleted=flow.alert_equipment_id, replacement=flow.replacement_id, nurse=nurse_id)
    )
    ctx.logger.info(
        f"oxygen_swap_complete: {flow.alert_equipment_id}->{flow.replacement_id} at {flow.bed_id} "
        f"via {nurse_id} (flow={flow.flow_id})"
    )
    # @spec OXY-FLOW-006 — confirm to the chat user (clear-on-completion, decision R2-D).
    await _finish_oxygen(ctx, flow.flow_id, format_oxygen_confirmation(flow.bed_id, flow.replacement_id, nurse_id))


orchestrator.include(chat, publish_manifest=True)
