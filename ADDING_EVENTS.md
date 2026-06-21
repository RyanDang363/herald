# Adding New Events to the ER Twin

A practical reference for extending the ER Twin with new events. Covers the current hardcoded
approach (what you have to touch today) and a proposed event-registry pattern that would make
additions faster and more isolated.

---

## How Events Work Today

Every event in the system flows through a single chain:

```
ASI:One chat message
  → ChatMessage handler (handle_chat)
    → CommandGate (serializes one command at a time)
      → _dispatch_command  ← ALL event logic branches live here
        → (sync)  emit replay + send chat reply → gate freed
        → (async) fire uAgent messages → gate freed in terminal @on_message handler
```

The Orchestrator (`er_twin/agents/orchestrator.py`) is the **only** file with public routing logic.
Every other agent is a private Bureau member that only responds to messages the Orchestrator sends.

### The three current events

| Intent key | Trigger keywords | Transport | Synchronous? |
|---|---|---|---|
| `intake` | `"chest pain"`, `"new patient arrived"` | In-process (direct function calls) | Yes — gate freed immediately |
| `oxygen` | `"oxygen is dropping"`, `"oxygen"` | Real async uAgent messages (4 hops) | No — gate freed in `on_dispatch` |
| `summary` | `"what's happening in the er"`, `"show me what"`, `"status summary"` | In-process, read-only | Yes |

---

## What You Must Touch to Add a New Event (Current Approach)

There are **8 places** across 4+ files. None of them are optional.

### 1. `er_twin/protocols.py` — define message contracts

Every new event needs request/response `Model` pairs for each agent hop. Follow the naming
convention: `{Noun}{Verb}Request` / `{Noun}{Verb}Response`.

```python
# er_twin/protocols.py

# --- Event N: Your New Event ---

class YourEventRequest(Model):
    patient_id: str
    some_field: str
    flow_id: str = ""          # required for async multi-hop events

class YourEventResponse(Model):
    result: str
    accepted: bool
    flow_id: str = ""
```

### 2. `er_twin/agents/your_agent.py` — write the entity agent

Each entity involved in the event needs pure domain functions (testable without uAgents) plus
`@agent.on_message` handlers that call them. Keep them strictly separated:

```python
# er_twin/agents/your_agent.py

# --- Pure domain functions (unit-testable) ---

def do_the_thing(store: StorageInterface, target_id: str) -> dict:
    """Pure logic — no ctx, no uAgents, just store reads/writes."""
    ...

# --- uAgent message handler ---

def make_your_event_handler(agent: Agent, store: StorageInterface):
    @agent.on_message(YourEventRequest)
    async def handle_your_event(ctx: Context, sender: str, msg: YourEventRequest):
        result = do_the_thing(store, msg.some_field)
        await ctx.send(sender, YourEventResponse(
            result=result["value"], accepted=True, flow_id=msg.flow_id
        ))
```

### 3. `er_twin/addresses.py` — register a deterministic address

Each new agent needs a seed-derived address so the Orchestrator can reach it without discovery.

```python
# er_twin/addresses.py
YOUR_AGENT_ID = "your_agent"
YOUR_AGENT_ADDRESS = address_for(YOUR_AGENT_ID)
```

### 4. `er_twin/agents/orchestrator.py` — 4 places inside this one file

#### 4a. Add trigger keywords to `_INTENT_KEYWORDS`

```python
_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "intake":     ("chest pain", "new patient arrived"),
    "oxygen":     ("oxygen is dropping", "oxygen"),
    "summary":    ("what's happening in the er", "show me what", "status summary"),
    "your_event": ("your trigger phrase", "alternate phrase"),  # ← add here
    "ping":       ("ping",),
}
```

Order matters: more specific phrases must come before generic ones.

#### 4b. Add a mock fallback to `MOCK_REPLIES`

```python
MOCK_REPLIES: dict[str, str] = {
    "intake":     "...",
    "oxygen":     "...",
    "summary":    "...",
    "your_event": "Your event completed successfully (mock).",  # ← add here
}
```

#### 4c. If async: define a flow-tracking dataclass (like `OxygenFlow`)

```python
@dataclass
class YourEventFlow:
    flow_id: str
    target_id: str
    session_id: str | None = None
    chat_sender: str | None = None
    status: str = "started"
    lines: list[dict] = field(default_factory=list)

your_event_flows: dict[str, YourEventFlow] = {}
```

#### 4d. Add a branch in `_dispatch_command`

For a **synchronous** (in-process) event:

```python
if intent == "your_event":
    if _store is None:
        await _send_chat(ctx, cmd.sender, MOCK_REPLIES["your_event"])
        return True
    outcome = run_your_event(_store, ...)         # pure orchestration function
    lines = [_replay.log(_store, "your_event", ...) for m in outcome["milestones"]]
    _emit_replay(ctx, "your_event", lines)
    await _send_chat(ctx, cmd.sender, outcome["confirmation"])
    return True                                    # ← True = gate freed now
```

For an **async** (multi-hop uAgent message) event:

```python
if intent == "your_event":
    if _store is None:
        await _send_chat(ctx, cmd.sender, MOCK_REPLIES["your_event"])
        return True
    _session_senders.remember(cmd.session_id, cmd.sender)
    flow = YourEventFlow(
        flow_id=flow_id, target_id=...,
        session_id=cmd.session_id, chat_sender=cmd.sender,
    )
    your_event_flows[flow_id] = flow
    await ctx.send(address_for(YOUR_AGENT_ID), YourEventRequest(..., flow_id=flow_id))
    return False                                   # ← False = gate freed later in @on_message
```

#### 4e. If async: add the terminal `@on_message` handler

```python
@orchestrator.on_message(YourEventResponse)
async def on_your_event_done(ctx: Context, sender: str, msg: YourEventResponse):
    flow = your_event_flows.get(msg.flow_id)
    if flow is None or flow.status == "done":
        return  # stale/duplicate — no-op
    flow.status = "done"
    # apply mutations, log milestones, emit replay...
    await _finish_your_event(ctx, flow.flow_id, "Your event confirmed.")
```

### 5. `er_twin/replay.py` — register the incident type

```python
INCIDENT_TYPES: dict[str, str] = {
    "intake":     "patient_intake",
    "oxygen":     "low_oxygen_alert",
    "summary":    "er_status_summary",
    "your_event": "your_event_type",    # ← add here
}

VISUAL_STYLE: dict[str, str] = {
    ...,
    "your_event_type": "cinematic ER style description for Pika prompt",
}
```

### 6. `er_twin/main.py` — add the new agent to the Bureau

```python
your_agent = YourAgentModule.make_agent(store)
bureau.add(your_agent)
```

### 7. `docs/specs/er-events-specs.md` — write EARS specs

Per the IDD process in CLAUDE.md, specs come before code. Add a new section following the
pattern of `INTAKE-*` / `OXY-*` / `SUMM-*`. Minimum required:

- `YOUR-FLOW-001` — trigger to first agent send
- `YOUR-FLOW-00N` — terminal action → chat reply
- `YOUR-ERR-001` — primary failure path
- `YOUR-IDEM-001` — idempotency (what happens if the same trigger fires twice)
- `YOUR-STATE-001` — what state changes and how

### 8. `tests/test_event_your_event.py` — write TDD tests

Tag every test with `# @spec YOUR-FLOW-001` etc. Test the pure domain functions directly against
`InMemoryStore` — no uAgents needed. Cover the happy path, every error branch, and idempotency.

---

## Human-in-the-Loop Gate Pattern

Based on how real ER systems distribute authority (ESI triage is nurse-owned, FDA classifies
autonomous clinical software differently from reviewable decision support), new events should
follow one of three levels of automation based on urgency:

| Time pressure | Pattern | Implementation |
|---|---|---|
| **Minutes** (intake, discharge, transfers) | Propose → human approves → commit | Keep session open (`end_session=False`), store `PendingProposal`, second chat message commits |
| **Seconds** (oxygen, deterioration alerts) | Act → human can veto | Execute immediately, offer `[STOP]` / `[ESCALATE]` reply; use `_watchdog` timeout |
| **None** (summary, queries) | Pure read-only display | No gate, `return True` synchronously |

The session-open path already exists — `_send_chat(..., end_session=False)` — and `CommandGate`
already holds through multi-message lifecycles. A `PendingProposal` dataclass and a
`plan_/commit_` split on your orchestration function is all that's needed to implement the gate.

---

## Proposed Event Registry Pattern

**Status: implemented.** The registry lives in `er_twin/events/` with `EventHandler` subclasses registered in `EVENT_REGISTRY`. `_dispatch_command` delegates to the registry; adding a new event is one handler file + one registry entry.

### The interface

```python
# er_twin/events/base.py
from abc import ABC, abstractmethod
from er_twin.storage import StorageInterface
from uagents import Context
from dataclasses import dataclass

@dataclass
class PendingCommand:
    sender: str
    session_id: str
    text: str
    flow_id: str

class EventHandler(ABC):
    """One subclass per ER event. Registered by key in EVENT_REGISTRY."""

    keywords: tuple[str, ...]       # trigger phrases (word-boundary matched)
    mock_reply: str                 # fallback when no store is wired
    incident_type: str              # for replay.INCIDENT_TYPES
    visual_style: str               # for replay.VISUAL_STYLE

    @abstractmethod
    async def dispatch(
        self,
        ctx: Context,
        cmd: PendingCommand,
        store: StorageInterface,
    ) -> bool:
        """Start the event flow.
        Return True if synchronous (gate frees now).
        Return False if async (gate freed in a terminal @on_message handler).
        """
        ...
```

### The registry

```python
# er_twin/events/registry.py
from er_twin.events.intake import IntakeHandler
from er_twin.events.oxygen import OxygenHandler
from er_twin.events.summary import SummaryHandler

EVENT_REGISTRY: dict[str, EventHandler] = {
    "intake":  IntakeHandler(),
    "oxygen":  OxygenHandler(),
    "summary": SummaryHandler(),
}
```

### The simplified `_dispatch_command`

```python
async def _dispatch_command(ctx: Context, cmd: PendingChatCommand, flow_id: str) -> bool:
    intent = resolve_command(cmd.text)
    handler = EVENT_REGISTRY.get(intent)
    if handler is None:
        await _send_chat(ctx, cmd.sender, CLARIFICATION)
        return True
    if _store is None:
        await _send_chat(ctx, cmd.sender, handler.mock_reply)
        return True
    pending = PendingCommand(cmd.sender, cmd.session_id, cmd.text, flow_id)
    return await handler.dispatch(ctx, pending, _store)
```

### Adding a new event under the registry pattern

With this in place, a new event is **one new file** + **one registry entry**:

```python
# er_twin/events/discharge.py
from er_twin.events.base import EventHandler, PendingCommand
from er_twin.agents import patient, bed, nurse

class DischargeHandler(EventHandler):
    keywords = ("discharge patient", "patient is ready to go home")
    mock_reply = "Patient discharged. Bed freed for incoming patients."
    incident_type = "patient_discharge"
    visual_style = "calm, resolved ER discharge sequence"

    async def dispatch(self, ctx, cmd, store) -> bool:
        # pure orchestration logic here, isolated from all other events
        ...
        return True
```

```python
# er_twin/events/registry.py  (add one line)
from er_twin.events.discharge import DischargeHandler
EVENT_REGISTRY["discharge"] = DischargeHandler()
```

`_dispatch_command`, `INCIDENT_TYPES`, `VISUAL_STYLE`, `MOCK_REPLIES`, and `_INTENT_KEYWORDS`
require **no changes** — the registry drives all of them.

---

## Checklist for a New Event

Use this before marking any new event "done":

- [ ] EARS specs written in `docs/specs/er-events-specs.md` (FLOW, ERR, IDEM, STATE)
- [ ] Message models added to `er_twin/protocols.py`
- [ ] Entity agent pure functions + `@on_message` handler written
- [ ] Deterministic address registered in `er_twin/addresses.py`
- [ ] Agent added to `Bureau` in `er_twin/main.py`
- [ ] Intent keywords added (registry entry or `_INTENT_KEYWORDS`)
- [ ] `_dispatch_command` branch added (or registry entry dispatches it)
- [ ] Replay incident type + visual style registered in `er_twin/replay.py`
- [ ] Human-in-the-loop gate level decided (approve / veto-window / none)
- [ ] Tests in `tests/test_event_<name>.py`, each tagged `# @spec <SPEC-ID>`
- [ ] `USE_MOCK` path verified (mock reply + no store fallback)
- [ ] `.env.example` updated if new env vars introduced
- [ ] Demo trigger phrase rehearsed (deterministic, pre-filled in TEAM.md)
