# ER Room Digital Twin

An autonomous digital twin of a hospital emergency room. Every physical entity — patient, nurse, doctor, bed, equipment — is modeled as a **uAgent** running in a single [Fetch.ai Bureau](https://fetch.ai/). A single `OrchestratorAgent` (reachable through ASI:One) receives natural-language commands, reasons with the ASI:One LLM, and dispatches real asynchronous uAgent messages to coordinate the ER in real time.

> This is not a dashboard that shows data. It is a system that **acts**.

---

## Getting Started

**Prerequisites:** Python 3.11+, [`uv`](https://docs.astral.sh/uv/) (`brew install uv`).

```bash
# 1. Clone and enter the repo
git clone https://github.com/RyanDang363/berk-ai-hackathon.git
cd berk-ai-hackathon

# 2. Set up environment variables
cp .env.example .env
# Edit .env — for a no-API-key local run, leave USE_MOCK=true

# 3. Install dependencies
uv sync

# 4. Run (mock mode — no API keys needed)
USE_MOCK=true uv run python -m er_twin.main

# 5. Run the tests
uv run pytest
```

**Mock mode (`USE_MOCK=true`)** swaps in deterministic keyword intent routing instead of the ASI:One LLM, `InMemoryStore` instead of Redis, and `NoopMemory` instead of Iris — but still runs the **real** agent coordination in-process over deterministically seeded state. Replies are state-derived and reproducible with no API keys.

**With API keys (`USE_MOCK=false`):** set `ASIONE_API_KEY`, `REDIS_URL`, and `AGENT_MEMORY_*` in `.env` for the live ASI:One LLM, Redis-backed state, and Iris agent memory.

**Architecture details:** see [ARCHITECTURE.md](ARCHITECTURE.md) for the subsystem map, message flows, and design decisions.

---

## The Problem

Emergency rooms operate in controlled chaos — every room, patient, nurse, doctor, and piece of equipment is a moving variable:

- **Reactive triage** — staff only respond after bottlenecks form
- **No real-time resource awareness** — nurses waste time locating equipment
- **Manual bed assignment** — slow and error-prone under surge conditions
- **Critical event delays** — no autonomous escalation when a patient deteriorates
- **Siloed systems** — no single source of truth for room, staff, and equipment state

---

## Architecture

**One process, one `Bureau`.** The public `OrchestratorAgent` (`mailbox=True`, Chat Protocol, reachable from ASI:One) runs **inside** the same Bureau as all private ER entity agents. They communicate over in-process uAgent messaging — no cross-process hop, no Almanac overhead.

```
                ASI:One  (public chat)
                   │  ChatMessage
                   ▼
      ┌─────────────────────────────────────────────────────────┐
      │  ONE Bureau · ONE process · ONE asyncio event loop      │
      │                                                         │
      │   OrchestratorAgent  ──── in-process ctx.send ────►    │
      │   (mailbox + Chat Protocol)                             │
      │         │                                               │
      │         ▼                                               │
      │   Admissions · Triage · Patient×3 · Bed×4 ·            │
      │   Nurse×2 · Doctor×2 · Equipment                       │
      │         │                                               │
      │         ▼                                               │
      │   StorageInterface      MemoryInterface                 │
      │   (InMemory|Redis)      (Noop|Iris)                     │
      └──────────┬──────────────────────────────────────────────┘
                 │ er:events                    out/replay/*.json
                 ▼                                    ▼
          Dashboard (FastAPI)              Replay timeline (/replay/…)
          co-hosted in-process
```

**State** lives behind a `StorageInterface` (InMemoryStore first, RedisStore via `REDIS_URL`). **Memory** lives behind a `MemoryInterface` (NoopMemory or Iris). The dashboard is co-hosted on the same asyncio event loop and reads the live store directly.

**Two write paths (intentional hybrid).** Chat commands (ASI:One or `USE_MOCK`) run as async uAgent message hops correlated by `flow_id`. Dashboard confirm/resolve call the same domain functions on the shared store directly — FastAPI handlers have no uAgent `Context` to `ctx.send`. Both paths leave the ER in the same state.

### Key Architecture Decisions

| Decision | Rationale |
|---|---|
| **Single-process Bureau** | One process + one event loop = one seam to debug. The Orchestrator (`mailbox=True`) is a Bureau member; entity agents are messaged in-process. |
| **Only Orchestrator on Agentverse** | Private agents have no mailbox and no Agentverse profile. Patient records stay in the local process. |
| **StorageInterface abstraction** | One interface (`get / set / update / delete / list_ids / publish`) with two backends. InMemoryStore is the default; RedisStore is a zero-handler-change swap via `REDIS_URL`. |
| **Async, fire-and-forget messaging** | Chat-path `ctx.send` calls return immediately; replies arrive in separate `@on_message` handlers and are correlated by `flow_id`. |
| **CommandGate serialization** | The Orchestrator runs one chat command at a time; new commands are FIFO-queued while one is in flight. A 30-second watchdog releases the gate if a reply never lands. |
| **Dashboard co-hosted** | The FastAPI dashboard is scheduled on the Bureau's existing event loop (`create_task` + `bureau.run()`). The shared store is injected directly — the floor map reads live state. Commands stay on chat; the dashboard is a live view plus confirm/resolve. |
| **IrisMemory for agent memory** | Iris (Redis Agent Memory) appends session events for long-term semantic recall. Recording and recall are best-effort and non-fatal — a memory failure never aborts a live command. |

---

## The Three Events

Each event is triggerable via a natural-language command to the `OrchestratorAgent` through ASI:One.

| Event | Trigger Phrase | Agent Flow |
|---|---|---|
| **1. Patient Intake** | *"A new patient arrived with chest pain"* | Orchestrator → AdmissionsAgent (intake + MRN) → TriageAgent (acuity) → BedAgent (assign) → NurseAgent + DoctorAgent (assign) → confirmation to chat |
| **2. Low Oxygen Alert** | *"Bed 3's patient oxygen is dropping"* | EquipmentAgent lowers supply + emits `LowSupplyAlert` → Orchestrator finds replacement unit → NurseAgent dispatched → oxygen swap applied → status confirmation |
| **3. Status Summary** | *"Show me what's happening in the ER"* | Orchestrator reads live state across all agents → synthesizes summary via ASI:One LLM → returns to chat |

Events 1 and 2 are async uAgent pipelines on the **chat** path (multi-hop `ctx.send` correlated by `flow_id`). Event 3 is a synchronous, read-only store query. Dashboard confirm/resolve for intake and discharge apply the same domain mutations without going through the message bus.

---

## Agent Roster

> Instance counts stay small so a local run is deterministic: 3 PatientAgents, 2 NurseAgents, 2 DoctorAgents, 4 BedAgents, a handful of EquipmentAgents.

| Agent | Responsibility |
|---|---|
| **OrchestratorAgent** | Mailbox + Chat Protocol + ASI:One reasoning. Only agent on Agentverse. Dispatches uAgent messages to all Bureau agents; serializes commands via CommandGate. |
| **AdmissionsAgent** | Patient intake: deduplication by MRN/name, EHR enrichment, patient slot registration. |
| **TriageAgent** | Chief-complaint → acuity score (ESI 1–5) + specialty routing. |
| **PatientAgent** (×3 pooled) | Tracks acuity, vitals, status, assigned bed, and care team. Pool of 3 reusable slots; `bind` / `discharge` manage lifecycle. |
| **BedAgent** (×4) | Tracks occupancy, specialty, attached equipment. Responds to assign and release requests. |
| **NurseAgent** (×2) | Tracks availability, assignments, location. Accepts dispatch and release requests. |
| **DoctorAgent** (×2) | Tracks specialty, load (cap 3), assignments. Paged for acuity ≤ 2 patients. |
| **EquipmentAgent** | One agent per device (oxygen tank, defibrillator). Tracks supply level and location; emits `LowSupplyAlert` autonomously. |

---

## Running Commands

```bash
# Start the full system (Bureau + dashboard co-hosted)
USE_MOCK=true uv run python -m er_twin.main

# Bureau only (no dashboard)
USE_MOCK=true uv run python -m er_twin.main --no-dashboard

# One-time mailbox bootstrap (needed once before connecting to ASI:One)
uv run python -m er_twin.main --connect-mailbox

# Dashboard standalone (fixture data, no Bureau needed)
uvicorn dashboard.server:app --port 8050

# Tests
uv run pytest

# Lint / format
uv run ruff check .
uv run ruff format .
```

---

## Technical Stack

| Component | Detail |
|---|---|
| **Language** | Python 3.11+ (pinned `<3.13`; 3.14 breaks `uagents==0.25.2` event-loop init) |
| **Agent framework** | `uagents` + `uagents-core`; Bureau for local agents; Chat Protocol for Orchestrator only |
| **Orchestrator brain** | ASI:One LLM via API (`asi1-mini`); `USE_MOCK=true` swaps in deterministic keyword routing |
| **State** | `StorageInterface` — `InMemoryStore` (default) or `RedisStore` (via `REDIS_URL`) |
| **Agent memory** | `MemoryInterface` — `NoopMemory` (default) or `IrisMemory` (via `AGENT_MEMORY_*`) |
| **Dashboard** | FastAPI + uvicorn, co-hosted in-process; session auth; optional Google OAuth |
| **Tooling** | `uv` (deps), `ruff` (lint/format), `pytest` + `pytest-asyncio` (tests) |
| **Secrets** | `.env` (never commit) + `.env.example` — keys: `ASIONE_API_KEY`, `REDIS_URL` (optional), `AGENT_MEMORY_*` (optional) |

---

## Data

This prototype uses synthetic patient data only. Entity agents run in-process and are not registered on Agentverse; the Orchestrator is the only public surface.
