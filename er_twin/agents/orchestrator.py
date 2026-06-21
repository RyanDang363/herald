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
import logging
import re
import time
from collections import deque
from dataclasses import dataclass
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
from er_twin.addresses import seed_for
from er_twin.agents import admissions, bed, doctor, nurse, patient, triage
from er_twin.config import settings
from er_twin.display import display
from er_twin.events.base import DispatchContext, PendingCommand as EventPendingCommand, PendingProposal
from er_twin.events.registry import EVENT_REGISTRY, all_keywords, mock_replies
from er_twin.memory import MemoryInterface, NoopMemory
from er_twin.oxygen_coord import (
    cleanup_oxygen,
)
from er_twin.oxygen_flow import OxygenFlow
from er_twin.protocols import (
    EquipmentLocateResponse,
    LowSupplyAlert,
    PingResponse,
    StaffDispatchResponse,
)
from er_twin.storage import StorageInterface

ORCHESTRATOR_AGENT_ID = "orchestrator"

# Module logger for best-effort paths that have no `ctx` in scope (e.g. `_log_milestone`).
_logger = logging.getLogger(__name__)

# --- Intent resolution (USE_MOCK hardcoded lookup, ORCH-LLM-003) ---

# Each intent maps to trigger substrings (driven by EVENT_REGISTRY).
_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = all_keywords()

# No-store fallback replies, referenced by the intake/oxygen/summary branches only when no shared store
# is wired (never in normal operation — main.py always injects one). The real replies are now state-
# derived; the summary string here is illustrative-only (decision R2-F) and never the shipped answer.
# `ping` is intentionally absent: it always round-trips through the stub (ORCH-SKEL-001), so its
# reply is the stub's live PingResponse text, never a canned string.
MOCK_REPLIES: dict[str, str] = mock_replies()

CLARIFICATION = (
    "I'm not sure what you'd like me to do. Try: 'patient intake MRN-0005', "
    "'Bed 3's patient oxygen is dropping', 'discharge patient MRN-0002', "
    "'resolve evt-0001', or 'Show me what's happening in the ER'."
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


def resolve_intent(text: str) -> str:
    """Pure USE_MOCK lookup: map chat text to an intent key, or ``"unknown"`` (ORCH-LLM-003)."""
    lowered = text.lower()
    for intent, keywords in _INTENT_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(keyword)}\b", lowered) for keyword in keywords):
            return intent
    return "unknown"


# ASI:One LLM intent resolution (ORCH-LLM-001). ASI:One is OpenAI-compatible — point the OpenAI SDK at
# its base URL and use `asi1-mini` (fastest/cheapest; classification is a short deterministic task per
# fetch-ai-documentation/models.md). The system prompt constrains the reply to a single intent token.
_ASIONE_BASE_URL = "https://api.asi1.ai/v1"
_ASIONE_MODEL = "asi1-mini"
# Hard per-request budget for the intent call. Short on purpose: well under COMMAND_TIMEOUT_SECONDS so a
# stalled ASI:One connection degrades to the deterministic lookup fast instead of hanging (ORCH-LLM-002).
_ASIONE_TIMEOUT_SECONDS = 8.0
_INTENT_SYSTEM_PROMPT = (
    "You classify a hospital ER operator's chat message into exactly one intent token. "
    "Reply with ONLY one lowercase word, no punctuation or explanation:\n"
    "- intake   : a new patient is arriving/has arrived or needs admission or triage\n"
    "- oxygen   : a patient's oxygen/SpO2 is dropping, or an oxygen unit is low/failing\n"
    "- discharge: a patient is ready to leave or be discharged (outtake)\n"
    "- resolve  : close/resolve a current event (e.g. resolve evt-0001)\n"
    "- summary  : a request for ER status, an overview, or what's currently happening\n"
    "- ping    : a connectivity or liveness test\n"
    "- unknown : anything that fits none of the above"
)


def _parse_llm_intent(raw: str) -> str:
    """Map a raw ASI:One reply to a known intent token, or raise ValueError (ORCH-LLM-001).

    Tolerant of a model that wraps the token in a sentence: returns the first known intent that appears
    as a whole word; an explicit `unknown` maps through; anything else raises so `resolve_command`
    degrades to the deterministic keyword lookup rather than mis-dispatching."""
    lowered = raw.lower()
    for intent in _INTENT_KEYWORDS:  # intake, oxygen, summary, ping (insertion order = priority)
        if re.search(rf"\b{intent}\b", lowered):
            return intent
    if re.search(r"\bunknown\b", lowered):
        return "unknown"
    raise ValueError(f"ASI:One returned no recognizable intent: {raw!r}")


def _resolve_via_llm(text: str) -> str:
    """Resolve an intent through the ASI:One LLM (ORCH-LLM-001).

    Raises on a missing key or any client/parse failure so `resolve_command` exercises the documented
    fallback to the deterministic keyword lookup (ORCH-LLM-002). The `openai` import is local so the
    USE_MOCK path never pays for it.
    """
    if not settings.asione_api_key:
        raise RuntimeError("ASIONE_API_KEY not set; using deterministic intent lookup")
    from openai import OpenAI

    # Fail fast: intent classification is on the chat critical path, so a connection error / rate-limit
    # must degrade to the deterministic lookup immediately (ORCH-LLM-002), not stall on the SDK's default
    # 600s timeout + 2 silent retries. A short timeout and no retries keep the fallback within the 30s
    # COMMAND_TIMEOUT_SECONDS watchdog budget.
    client = OpenAI(
        base_url=_ASIONE_BASE_URL,
        api_key=settings.asione_api_key,
        timeout=_ASIONE_TIMEOUT_SECONDS,
        max_retries=0,
    )
    response = client.chat.completions.create(
        model=_ASIONE_MODEL,
        messages=[
            {"role": "system", "content": _INTENT_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        max_tokens=16,
        temperature=0,
    )
    return _parse_llm_intent(str(response.choices[0].message.content))


# ASI:One prepends an "@<agent-address>" mention to chat it routes to an agent (e.g.
# "@agent1qty... A new patient arrived with chest pain"). It's transport-level routing noise: the LLM
# intent path tolerates it, but exact-match lookups (MOCK_INTAKE) and text parsing (bed id) must see the
# operator's actual words. Strip a leading uAgents mention (`@agent1...`) at ingestion.
_AGENT_MENTION_RE = re.compile(r"^\s*@agent1[0-9a-z]+\s+", re.IGNORECASE)


def strip_agent_mention(text: str) -> str:
    """Remove a leading ``@agent1...`` mention that ASI:One prepends when routing chat to an agent.

    @spec ORCH-CHAT-002 — the operator's words drive intent + intake payload selection; the routing
    mention is noise. Idempotent and a no-op when no mention is present.
    """
    return _AGENT_MENTION_RE.sub("", text).strip()


def lookup_mock_intake(text: str) -> dict | None:
    """Find a MOCK_INTAKE payload for chat text, tolerant of casing and any wrapping around the phrase.

    Backstops `strip_agent_mention`: even if a routing mention or trailing text survives, a known trigger
    phrase appearing anywhere in the message still selects the right patient payload (so chest-pain chat
    admits Jordan Lee, not an "Unknown Patient")."""
    lowered = text.lower()
    for phrase, data in MOCK_INTAKE.items():
        if phrase.lower() in lowered:
            return data
    return None


# An MRN token as it appears in chat ("MRN-0007", case-insensitive). Used to enrich intake from the EHR.
_MRN_RE = re.compile(r"\bMRN-\d+\b", re.IGNORECASE)


def extract_mrn(text: str) -> str:
    """Extract an `MRN-NNNN` token from chat text (normalized upper-case), or ``""`` if absent.

    @spec EHR-FLOW-001 — when the chat carries an MRN it rides on `PatientIntakeRequest.mrn`; when it
    does not, the empty string flows through and `build_live_record` mints the next sequential MRN.
    """
    match = _MRN_RE.search(text)
    return match.group(0).upper() if match else ""


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


def run_intake(
    store: StorageInterface, name: str, chief_complaint: str, vitals: dict, mrn: str = "",
    on_milestone=None,
) -> dict:
    """Run the full intake flow and return the outcome (+ confirmation + milestone log).

    `on_milestone(action, target, detail)` (optional) is invoked synchronously at each milestone, right
    after that step mutated the store — so a caller can capture a live `er:events` line + a full-state
    snapshot at the *real* moment of the milestone (REPLAY-SNAP-001), instead of only the final state.
    Default `None` keeps the function pure for existing callers (tests, async wrapper).

    @spec INTAKE-FLOW-001 @spec INTAKE-FLOW-002 @spec INTAKE-BIND-001 @spec INTAKE-FLOW-003
    @spec INTAKE-FLOW-004 @spec INTAKE-FLOW-005 @spec INTAKE-FLOW-006 @spec INTAKE-FLOW-007
    @spec INTAKE-FLOW-008 @spec INTAKE-FLOW-009 @spec INTAKE-FLOW-010 @spec INTAKE-FLOW-011
    @spec INTAKE-STATE-001 @spec INTAKE-BIND-003 @spec INTAKE-ERR-002 @spec INTAKE-ERR-003
    @spec INTAKE-ERR-004 @spec INTAKE-IDEM-001
    """
    milestones: list[dict] = []

    def log(action: str, target: str | None = None, **detail) -> None:
        milestones.append({"action": action, "target": target, "detail": detail})
        if on_milestone is not None:
            on_milestone(action, target, detail)

    log("intake_received", detail=chief_complaint)
    # @spec EHR-FLOW-002 — AdmissionsAgent enriches the record from the master EHR before persisting.
    patient_id, record, created = admissions.intake(store, name, chief_complaint, vitals, mrn)
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


# --- Agent + chat protocol wiring ---

orchestrator = Agent(
    name="ER Twin Orchestrator",
    seed=seed_for(ORCHESTRATOR_AGENT_ID),
    mailbox=True,
    publish_agent_details=True,
    network="testnet",
    handle="er-herald",
    description=(
        "Autonomous digital twin of a hospital emergency room, built on Fetch.ai uAgents. "
        "Chat to drive it: \"patient intake MRN-0005\", "
        "\"Bed 3's patient oxygen is dropping\", or \"Show me what's happening in the ER\". "
        "Synthetic demo data only — no real patient health information."
    ),
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
session_pending: dict[str, PendingProposal] = {}

# Monotonic per-run correlation id source
_flow_counter = 0
# A command whose terminal reply never arrives must not wedge the gate; release it after this long.
COMMAND_TIMEOUT_SECONDS = 30

# Shared state store, injected by main.py so the Orchestrator and entity agents read/write one store.
_store: StorageInterface | None = None

# Agent memory (Iris in live mode, Noop under USE_MOCK / no creds), injected by main.py. Defaults to a
# NoopMemory so the Orchestrator is safe even if main.py never calls set_memory (e.g. in unit tests).
_memory: MemoryInterface = NoopMemory()

# Incident replay recorder (Phase R): holds the per-run `seq` + incident counters, publishes milestone
# lines to `er:events`, and mints incident ids. Reset per process run (no wall-clock — LLD §9).
_replay = replay.ReplayRecorder()
# Directory the replay artifacts are written to (out/{incident_id}.json + latest brief + pika_prompt.md).
REPLAY_OUT_DIR = "out"


def set_store(store: StorageInterface) -> None:
    """Inject the shared store the Orchestrator coordinates over (called from main.py at startup)."""
    global _store
    _store = store


def set_memory(memory: MemoryInterface) -> None:
    """Inject the agent-memory backend (called from main.py at startup; defaults to NoopMemory)."""
    global _memory
    _memory = memory


def _record_memory(ctx: Context, text: str) -> None:
    """Append a one-line outcome to agent memory (MEM-FLOW-001).

    Best-effort: a memory-backend failure must never break the live command (mirrors `_emit_replay`),
    so it is logged and swallowed. Under `NoopMemory` this is a silent no-op (MEM-ERR-001)."""
    try:
        _memory.record_event(text)
    except Exception:  # noqa: BLE001 — memory is non-critical; never crash the command.
        ctx.logger.exception("memory record_event failed")


def _recall_memory(query: str) -> list[str]:
    """Recall relevant prior event facts from memory (MEM-FLOW-002); returns ``[]`` on any failure."""
    try:
        return _memory.recall(query)
    except Exception:  # noqa: BLE001 — degrade to no recalled context rather than crash the summary.
        return []


def _log_milestone(
    store: StorageInterface, event: str, actor: str, action: str,
    target: str | None = None, **detail,
) -> dict | None:
    """Publish a milestone line AND capture a full-state snapshot of the store — best-effort.

    @spec REPLAY-LOG-001 — the `er:events` line (unchanged shape) is published by `ReplayRecorder.log`.
    @spec REPLAY-SNAP-001 — the same call captures every entity record + a real wall-clock `ts`
    (`time.time()`, injected here so `replay.py` stays wall-clock-free) into the seq-keyed timeline used
    by the replay page / library. The published line carries no `ts` (REPLAY-LOG-002 untouched).

    The replay layer is **additive observation**, so — like `_emit_replay`/`_record_memory` — a transient
    backend fault (e.g. a `RedisStore` publish/read timeout) must NEVER abort the live command. On
    failure it logs and returns ``None``; the caller records no replay line for that milestone and the
    ER flow proceeds (and, for oxygen, still reaches `_finish_oxygen` after the swap).
    """
    try:
        line = _replay.log(store, event, actor, action, target, **detail)
    except Exception:  # noqa: BLE001 — replay capture is non-critical; never crash the live command.
        _logger.exception("replay milestone log failed (%s/%s)", event, action)
        return None
    try:
        _replay.snapshot(store, line["seq"], time.time(), action=action, actor=actor, target=target)
    except Exception:  # noqa: BLE001 — snapshot capture is best-effort observation.
        _logger.exception("replay snapshot failed (%s/%s)", event, action)
    return line


def _record_milestone(
    buf: list[dict], store: StorageInterface, event: str, actor: str, action: str,
    target: str | None = None, **detail,
) -> dict | None:
    """`_log_milestone` then append to `buf` only when a line was produced (skips a best-effort miss)."""
    line = _log_milestone(store, event, actor, action, target, **detail)
    if line is not None:
        buf.append(line)
    return line


def _emit_replay(ctx: Context, event: str, lines: list[dict]) -> str | None:
    """Export an incident's replay brief + snapshot timeline; return the incident id (or None).

    Best-effort: a replay-export failure must never break the live command, so it is logged and
    swallowed. Skips entirely when no store is wired or no milestone lines were recorded
    (REPLAY-BRIEF-003 — no empty artifacts)."""
    if _store is None or not lines:
        return None
    try:
        incident_id = _replay.next_incident_id(event)
        incident_type = replay.INCIDENT_TYPES[event]
        brief = replay.export_incident(
            lines, incident_id, incident_type, _store, out_dir=REPLAY_OUT_DIR
        )
        if brief is None:
            return None
        ctx.logger.info(f"replay brief written: {incident_id} -> {REPLAY_OUT_DIR}/")
        # @spec REPLAY-SNAP-003 @spec REPLAY-LIB-001 — write the full-state snapshot timeline
        # (with per-snapshot ts + library metadata) for the replay page and the /library.
        snapshots = _replay.snapshots_for(ln["seq"] for ln in lines)
        timeline = replay.export_incident_timeline(
            snapshots, incident_id, incident_type, brief["title"], brief["summary"],
            display=display, out_dir=REPLAY_OUT_DIR,
        )
        if timeline is not None:
            ctx.logger.info(
                f"replay timeline written: {incident_id} -> "
                f"{REPLAY_OUT_DIR}/{replay.REPLAY_SUBDIR}/ ({len(snapshots)} snapshots)"
            )
        return incident_id
    except Exception:  # noqa: BLE001 — replay export is non-critical; never crash the command.
        ctx.logger.exception("replay export failed")
        return None



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
    text = strip_agent_mention(text)  # drop ASI:One's "@agent1..." routing prefix before parsing
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
        from er_twin.events.base import PendingProposal

        pending = session_pending.get(cmd.session_id)
        if isinstance(pending, PendingProposal):
            handler = EVENT_REGISTRY.get(pending.event_type)
            if handler is not None:
                completed = await handler.resume(_make_dctx(ctx, cmd, flow_id), pending)
            else:
                completed = await _dispatch_command(ctx, cmd, flow_id)
        else:
            completed = await _dispatch_command(ctx, cmd, flow_id)
    except Exception as exc:  # noqa: BLE001 — never let a command crash the Orchestrator.
        ctx.logger.exception("command dispatch failed")
        await _send_chat(ctx, cmd.sender, f"Sorry — I hit an error handling that: {exc}")
        completed = True
    if completed:
        await _complete_command(ctx, flow_id)


def _make_dctx(ctx: Context, cmd: PendingChatCommand, flow_id: str) -> DispatchContext:
    """Build the shared dispatch context passed to event handlers."""
    ep = EventPendingCommand(sender=cmd.sender, session_id=cmd.session_id, text=cmd.text, flow_id=flow_id)
    return DispatchContext(
        ctx=ctx,
        cmd=ep,
        store=_store,
        replay=_replay,
        memory=_memory,
        session_pending=session_pending,
        oxygen_flows=oxygen_flows,
        in_flight_o2_dispatches=in_flight_o2_dispatches,
        session_senders=_session_senders,
        pending_ping_sessions=_pending_ping_sessions,
        send_chat=_send_chat,
        log_milestone=_log_milestone,
        record_milestone=_record_milestone,
        emit_replay=_emit_replay,
        record_memory=_record_memory,
        recall_memory=_recall_memory,
        new_flow_id=_new_flow_id,
        complete_command=_complete_command,
    )


async def _dispatch_command(ctx: Context, cmd: PendingChatCommand, flow_id: str) -> bool:
    """Resolve intent and dispatch via EVENT_REGISTRY."""
    intent = await asyncio.to_thread(resolve_command, cmd.text)
    ctx.logger.info(f"chat[{cmd.session_id[:8]}] flow={flow_id} resolved intent={intent!r}")

    handler = EVENT_REGISTRY.get(intent)
    if handler is None:
        await _send_chat(ctx, cmd.sender, CLARIFICATION)
        return True
    if _store is None and handler.mock_reply:
        await _send_chat(ctx, cmd.sender, handler.mock_reply)
        return True
    return await handler.dispatch(_make_dctx(ctx, cmd, flow_id))


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
    cleanup_oxygen(flow_id, oxygen_flows, in_flight_o2_dispatches, _session_senders)


async def _finish_oxygen(ctx: Context, flow_id: str, reply: str) -> None:
    """Legacy terminal path — delegated to OxygenHandler._finish via registry."""
    handler = EVENT_REGISTRY["oxygen"]
    dctx = _make_dctx(ctx, PendingChatCommand(sender="", session_id="", text=""), flow_id)
    await handler._finish(dctx, flow_id, reply)  # noqa: SLF001


@orchestrator.on_message(LowSupplyAlert)
async def on_low_supply(ctx: Context, sender: str, msg: LowSupplyAlert):
    await EVENT_REGISTRY["oxygen"].on_low_supply(_make_dctx(ctx, PendingChatCommand(sender=sender, session_id="", text=""), msg.flow_id or ""), msg)


@orchestrator.on_message(EquipmentLocateResponse)
async def on_locate(ctx: Context, sender: str, msg: EquipmentLocateResponse):
    await EVENT_REGISTRY["oxygen"].on_locate(_make_dctx(ctx, PendingChatCommand(sender=sender, session_id="", text=""), msg.flow_id), msg)


@orchestrator.on_message(StaffDispatchResponse)
async def on_dispatch(ctx: Context, sender: str, msg: StaffDispatchResponse):
    await EVENT_REGISTRY["oxygen"].on_dispatch(_make_dctx(ctx, PendingChatCommand(sender=sender, session_id="", text=""), msg.flow_id), msg)


orchestrator.include(chat, publish_manifest=True)
