# ER Twin — Architecture

How the system is built, from the public chat surface down to state, memory, and replay media. For
*intent* (the why), see [README.md](README.md) (HLD) and `docs/llds/`, `docs/specs/`. For *teammate
connection*, see [AGENT.md](AGENT.md). This file is the *how it actually works* map of the code.

> **One principle:** one process, one `Bureau`. A single public **OrchestratorAgent** (mailbox + Chat
> Protocol, reachable from ASI:One as `@er-herald`) coordinates a set of **private** ER entity agents
> over a shared `StorageInterface`. Only the Orchestrator is on Agentverse.

---

## 1. Runtime topology

```
                ASI:One  (public chat)
                   │  ChatMessage / ChatAcknowledgement
                   ▼
        ┌──────────────────────────────────────────────────────────────┐
        │  ONE Bureau · ONE process · ONE event loop                     │
        │                                                                │
        │   OrchestratorAgent  ──(in-process ctx.send / direct calls)──┐ │
        │   (mailbox + Chat Protocol, @er-herald)                      │ │
        │      │                                                       ▼ │
        │      │   Admissions · Triage · Patient×3 · Bed×4 ·             │
        │      │   Nurse×2 · Doctor×2 · Equipment · (Stub)               │
        │      ▼                                                         │
        │   StorageInterface  ──  MemoryInterface                        │
        │   (InMemory|Redis)      (Noop|Iris)                            │
        └───────────────┬───────────────────────────────┬──────────────┘
                        │ er:events + out/*.json          │
                        ▼                                  ▼
                 Dashboard (FastAPI, read-only)     Replay artifacts
                                                    → Claude Code CLI → Pika MCP (media)
```

- **Single-process default (`ORCH-SYS-001`)** — spike-proven on `uagents==0.25.2`
  (`spikes/mailbox_inside_bureau_spike.py`): a `mailbox=True` agent runs inside a `Bureau` and
  in-process messaging works. The **two-process split** (standalone Orchestrator + separate Bureau) is
  the documented **fallback only**, used if ASI:One/Agentverse smoke testing fails (README →
  *Architecture Alternatives and Fallbacks*).
- **Deterministic addresses (`ORCH-SYS-002`)** — every agent's address is derived from
  `{AGENT_SEED}-{role}` at *import time* ([addresses.py](er_twin/addresses.py)); no runtime Almanac
  discovery. The Orchestrator's address is stable across restarts, so its Agentverse mailbox persists.

---

## 2. Entry point & composition

[`er_twin/main.py`](er_twin/main.py) `main()` is the single entry point:

```
make_store()  ──►  RedisStore   if REDIS_URL set and USE_MOCK=false, else InMemoryStore
make_memory() ──►  IrisMemory   if AGENT_MEMORY_* set and USE_MOCK=false, else NoopMemory
ensure_seeded(store)            seed → read indexes back → re-seed once if beds/nurses missing
orch.set_store(store); orch.set_memory(memory)   inject shared backends (module globals)
build_bureau(store).run()       one Bureau: Orchestrator + Stub + all entity agents
```

- **Seeding** ([main.py](er_twin/main.py)): `seed_state()` lays clean inventory from each module's
  `init_state()`; `seed_baseline()` overlays the mid-shift demo scenario (p1 waiting, p2 on bed-3 with
  oxygen `o2_1`, nurse1 busy, doc2 assigned) so the oxygen and summary commands are demoable in any
  order. **`ensure_seeded()` is self-healing**: it reads the live index sets back and re-seeds once if
  core inventory is missing, and the boot banner prints the read-back counts (so a partial/failed seed
  is loud, not silent).
- **No concrete-backend imports** — agents only ever touch `StorageInterface` / `MemoryInterface`;
  backends are chosen by factories and injected.

---

## 3. The OrchestratorAgent (the only public surface)

[`er_twin/agents/orchestrator.py`](er_twin/agents/orchestrator.py). The only agent with a mailbox and
the Chat Protocol (`Protocol(spec=chat_protocol_spec)` — there is no importable `chat_proto`).

**Chat lifecycle (`ORCH-CHAT-002`):**
1. `ChatMessage` arrives → **acknowledge immediately** (`ChatAcknowledgement`).
2. **Strip the ASI:One mention** — ASI:One prepends `@agent1…` for routing; `strip_agent_mention()`
   removes it so downstream exact-match lookups see the operator's actual words.
3. **Resolve intent** (`resolve_command`): under `USE_MOCK` use the deterministic keyword lookup
   (`resolve_intent` over `_INTENT_KEYWORDS`, `ORCH-LLM-003`); otherwise call ASI:One
   (`_resolve_via_llm`, OpenAI-compatible `asi1-mini`, **8 s timeout + `max_retries=0`**) and **fall
   back to the keyword lookup on any error** (`ORCH-LLM-002`) — fast, never hangs. Runs off the event
   loop via `asyncio.to_thread`.
4. **Serialize** (`ORCH-SYS-003`): a `CommandGate` runs one command at a time; while busy, new commands
   are FIFO-enqueued and the user gets "I'm finishing the current ER action." A 30 s watchdog
   (`COMMAND_TIMEOUT_SECONDS`) releases the gate if a reply never lands.
5. **Dispatch** on intent: `ping` · `intake` · `oxygen` · `summary` · `unknown` (clarification,
   `ORCH-LLM-004`).

Async replies are correlated back to the right chat session via a `SessionSenders` map (+ a pending
FIFO for ping) and, for oxygen, by `flow_id`.

---

## 4. The three events

| Event | Mode | Path |
|---|---|---|
| **Intake** (Event 1) | **synchronous, in-process** | `run_intake()` over pure domain fns |
| **Oxygen** (Event 2) | **real async uAgent messaging** (mandatory Fetch showcase) | multi-hop `ctx.send` |
| **Summary** (Event 3) | **synchronous, read-only** | `build_status_summary()` |

### Event 1 — Patient intake (in-process)
Decision [`INTAKE_MODE=direct`](docs/decisions/2026-06-20-intake-orchestration-mode.md) is canonical and
demo-safe. `run_intake()` orchestrates pure domain functions over the shared store:

```
admissions.intake (dedupe by MRN/name, EHR-enrich, mint p{n}, status=waiting)
  → patient.bind_slot (bind an idle pooled PatientAgent; pool of 3)
  → triage.triage (chief_complaint → acuity ESI 1-5 + specialty)
  → bed.find_available_bed (prefer specialty, fall back to general)
  → nurse.find_available_nurse + assign (capacity 1/nurse)
  → doctor.find_available_doctor + page (load cap 3; for acuity ≤ 2)
```
The Orchestrator owns the status transitions (`waiting → in_triage → admitted`). Each step logs a
replay milestone and snapshots state. An optional `INTAKE_MODE=async` (same logic as explicit uAgent
messages) is deferred.

### Event 2 — Low-oxygen alert (async, the showcase)
Genuine fire-and-forget uAgent messaging across agents, correlated by `flow_id`:

```
chat "oxygen" → SimulateOxygenDropRequest → EquipmentAgent
   EquipmentAgent lowers supply_level + patient SpO₂, then AUTONOMOUSLY emits LowSupplyAlert
on_low_supply  → idempotency gate (in_flight_o2_dispatches, OXY-IDEM-001) → EquipmentLocateRequest
on_locate      → pick replacement unit → StaffDispatchRequest → NurseAgent
on_dispatch    → NurseAgent accepts → apply_oxygen_swap (equipment.swap_oxygen_unit + nurse.dispatch_nurse)
               → confirm to chat, export incident, release gate
```
Every hop is a separate `@on_message` handler (`ctx.send` returns immediately). Duplicate/late
responses are no-ops (`flow.status == "done"` guard). `OxygenFlow` context is keyed by `flow_id` so
overlapping alerts never clobber each other.

### Event 3 — Status summary (read-only)
`build_status_summary(store, alert_beds)` is a pure, store-derived template (decision R2-F): active
patients, bed occupancy, free/busy nurses, active O₂ alerts, most-urgent patient. It mutates nothing.
Under live memory it folds in recalled facts (`MEM-FLOW-002`).

The ping skeleton (`ORCH-SKEL-001`) proves the async pattern end-to-end: chat → `PingRequest` → Stub →
`PingResponse` in a separate handler → relay to chat.

---

## 5. Messaging model

- **Async, not request/response** (LLD §5): all `ctx.send` calls are fire-and-forget; replies arrive in
  separate `@on_message` handlers and are correlated by `flow_id` (oxygen) or the session map (ping).
- **Shared message models** live in [`er_twin/protocols.py`](er_twin/protocols.py) as uAgent `Model`
  classes in request/response pairs: `PingRequest/Response`, `PatientIntake*`, `PatientBind*`,
  `Triage*`, `BedAssign*`, `StaffAssign*`, `LowSupplyAlert`, `EquipmentLocate*`, `StaffDispatch*`,
  `SimulateOxygenDropRequest`. The intake skeleton models exist but the canonical `direct` flow calls
  the domain functions in-process rather than sending them; the **oxygen** models are the ones on the
  live wire.
- **Chat Protocol** (`uagents_core.contrib.protocols.chat`): `ChatMessage`, `ChatAcknowledgement`,
  `TextContent`, `EndSessionContent` — Orchestrator only.

---

## 6. State & memory

### Storage ([`er_twin/storage.py`](er_twin/storage.py))
`StorageInterface`: `get / set / update / list_ids / publish`. Agents depend on this interface only.

- **`InMemoryStore`** — process-local dict; zero dependencies; the `USE_MOCK` default.
- **`RedisStore`** — hashes keyed `er:{entity}:{id}`; index sets `er:index:{entity}` (so `list_ids`
  never needs `KEYS`/`SCAN`); event feed `er:events` as a **Redis Stream** (`XADD`, so the dashboard
  can replay history via `XRANGE`/`XREVRANGE`). **Writes are atomic** —
  `pipeline(transaction=True)` wraps `DEL+HSET+SADD` (set) / `HSET+SADD` (update) so a mid-pipeline
  network stall can't delete a key without recreating + indexing it. *(This was the root cause of the
  silent beds/nurses-vanishing bug, now fixed.)*
- `make_store()` selects the backend from `USE_MOCK` + `REDIS_URL`.

### Memory ([`er_twin/memory.py`](er_twin/memory.py))
`MemoryInterface`: `record_event / recall`. `IrisMemory` (Redis Agent Memory / Iris — appends session
events with UTC timestamps, semantic long-term recall) vs `NoopMemory` (silent). `make_memory()`
selects by `USE_MOCK` + `AGENT_MEMORY_*`. Recording/recall is **best-effort and non-fatal**
(`MEM-FLOW-001/002`, `MEM-ERR-001`) — a memory failure never aborts a live command.

### EHR ([`er_twin/ehr.py`](er_twin/ehr.py), `fixtures/ehr_master.json`)
Master patient chart keyed by **MRN** (person-scoped, stable across visits) — distinct from
`patient_id` (visit-scoped). Intake resolves an MRN (or mints one for a walk-in), loads history
(meds/conditions/allergies), and writes back new stubs with cache coherence (`EHR-FLOW-*`).

---

## 7. Replay & media pipeline

Deterministic milestone capture → on-disk artifacts → media, with **Pika never imported inside
`er_twin/`** (file-based boundary — a CLAUDE.md hard rule).

- **`ReplayRecorder`** ([`er_twin/replay.py`](er_twin/replay.py)) — one per process; a monotonic `seq`
  counter (no wall-clock in the event line, so runs are reproducible, `REPLAY-LOG-002`) and per-type
  incident counters. The Orchestrator's `_log_milestone` publishes a structured line to `er:events`
  *and* captures a full-state snapshot (real `ts`, keyed by `seq`, `REPLAY-SNAP-001`).
- **On completion**, `export_incident` writes a **brief** (`out/{incident_id}.json` +
  `out/incident_replay_brief.json` + `out/pika_prompt.md`) and a **timeline**
  (`out/replay/{incident_id}.json`). `incident_type ∈ {patient_intake, low_oxygen_alert,
  er_status_summary}`. Nothing is written if there were no milestones.
- **Pika** is driven *post-process* by the headless **Claude Code CLI** (`scripts/run_pika_replay.ps1`,
  `run_pika_keyframes.ps1`) with `--mcp-config .mcp.json` and an explicit `--allowedTools` allowlist
  (a non-empty `permission_denials` fails the run). Returned media URLs are written back into
  `out/replay/{id}.json`.
- **Frame capture** (`scripts/capture_replay_frames.py`, Playwright) drives the dashboard replay page
  to screenshot keyframes (capped to {start, end} for Pika's two-image interpolation).

### Dashboard ([`dashboard/`](dashboard/))
Read-only FastAPI app. `DASHBOARD_SOURCE ∈ {fixture, redis, sim}` selects the datasource. Endpoints:
`/api/state` (live snapshot + derived KPIs), `/api/events` (the `er:events` feed), `/api/replay/{id}`
(timeline playback, tweened by real `ts` deltas), `/api/library` (index of generated replays). It only
*reads* the same store the agents write — no command input by default.

---

## 8. Configuration & deployment

[`er_twin/config.py`](er_twin/config.py) (`pydantic-settings`, `.env`):

| Setting | Default | Effect |
|---|---|---|
| `USE_MOCK` | `true` | `true` → InMemoryStore + NoopMemory, deterministic, **no external calls** |
| `AGENT_SEED` | `er-twin-demo-seed` | derives every agent address (don't change → preserves the mailbox) |
| `REDIS_URL` | `""` | set + `USE_MOCK=false` → RedisStore |
| `AGENT_MEMORY_*` | `""` | set + `USE_MOCK=false` → IrisMemory |
| `INTAKE_MODE` | `direct` | canonical in-process intake (`async` deferred) |
| `DASHBOARD_SOURCE` | `fixture` | dashboard datasource |

`network="testnet"` is hardcoded on every agent to quiet Almanac warnings.

```bash
USE_MOCK=true uv run python -m er_twin.main     # deterministic local/demo run
uv run pytest                                   # tests
```

**Mailbox onboarding caveat:** the Agentverse Inspector can't onboard a Bureau, so the mailbox is
bootstrapped once with the standalone [`er_twin/connect_orchestrator.py`](er_twin/connect_orchestrator.py)
(same seed/address); the real Bureau runtime then reuses that mailbox. See [AGENT.md](AGENT.md).

---

## 9. Key invariants (traced to EARS specs)

- `DOMAIN-STATE-001/002/003` — a bed holds ≤1 patient; a patient holds ≤1 bed; a discharged patient
  can't be triaged without a new intake.
- `INTAKE-IDEM-001/002`, `OXY-IDEM-001` — intake dedupes by MRN/name; bed/nurse/doctor assignment and
  the oxygen swap are idempotent; duplicate oxygen alerts for the same unit are ignored.
- `ORCH-SYS-003` — exactly one chat command in flight at a time.
- Capacity: 3 patient slots, 4 beds, 2 nurses (1 patient each), 2 doctors (load cap 3), small equipment
  pool — kept small for a deterministic, judge-friendly demo.

Code and tests carry `# @spec <ID>` comments tracing back to these specs.
