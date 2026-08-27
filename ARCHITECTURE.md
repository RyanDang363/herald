# ER Twin — Architecture

How the implemented system is built, from the public chat surface down to state, memory, and replay.
For a quick project overview see [README.md](README.md).

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
        │  ONE Bureau · ONE process · ONE event loop                   │
        │                                                              │
        │   OrchestratorAgent  ──── in-process ctx.send ──────────►   │
        │   (mailbox + Chat Protocol, @er-herald)                      │
        │         │                                                    │
        │         ▼                                                    │
        │   Admissions · Triage · Patient×3 · Bed×4 ·                 │
        │   Nurse×2 · Doctor×2 · Equipment · (Stub)                   │
        │         │                                                    │
        │         ▼                                                    │
        │   StorageInterface       MemoryInterface                     │
        │   (InMemory | Redis)     (Noop | Iris)                       │
        └──────────┬───────────────────────────────────────────────────┘
                   │ er:events                    out/replay/*.json
                   ▼                                    ▼
            Dashboard (FastAPI)              Replay timeline (/replay/…)
            co-hosted in-process
            reads the same store (confirm/resolve write it directly)
```

- **Single-process default (`ORCH-SYS-001`)** — the public Orchestrator (`mailbox=True`) is a
  Bureau member; entity agents are messaged in-process on the same event loop.
- **Deterministic addresses (`ORCH-SYS-002`)** — every agent address is derived from
  `{AGENT_SEED}-{role}` at import time ([`er_twin/addresses.py`](er_twin/addresses.py)); no runtime
  Almanac discovery. The Orchestrator's address is stable across restarts, so its Agentverse
  mailbox persists.
- **Co-hosted dashboard** — the FastAPI/uvicorn app runs on the same event loop via `asyncio.gather`.
  The shared store is injected into `dashboard.datasource` on startup. The dashboard is a live
  view plus confirm/resolve; **commands enter through chat**, not a dashboard command bar.

**Two write paths.** Chat confirm/resolve/intake/discharge/oxygen run as uAgent message hops
(`ctx.send`, correlated by `flow_id`). Dashboard confirm/resolve call the same domain functions
(`commit_full_intake`, `commit_discharge`, `release_patient_resources`) on the shared store —
FastAPI has no uAgent `Context`. This is deliberate: one state model, two entry points.

---

## 2. Entry point & composition

[`er_twin/main.py`](er_twin/main.py) `main()` is the single entry point:

```
make_store()  ──►  RedisStore     if REDIS_URL set and USE_MOCK=false, else InMemoryStore
make_memory() ──►  IrisMemory     if AGENT_MEMORY_* set and USE_MOCK=false, else NoopMemory
ensure_seeded(store)              seed → read indexes back → re-seed once if beds/nurses missing
orch.set_store(store); orch.set_memory(memory)    inject shared backends (module globals)
datasource.set_live_store(store)  dashboard reads live state from the same store
bureau._loop.create_task(uvicorn dashboard); bureau.run()
```

Flags:
- `--no-dashboard` — runs Bureau only (no uvicorn); useful for headless / CI smoke tests.
- `--connect-mailbox` — runs the Orchestrator standalone (same seed → same address) so the
  Agentverse Inspector can connect a mailbox. Stop once the Inspector confirms, then run normally.
  Replaces the old `er_twin/connect_orchestrator.py` helper.

**Seeding** ([`main.py`](er_twin/main.py)): `seed_state()` lays clean inventory from each module's
`init_state()`; `seed_baseline()` overlays the mid-shift demo scenario (p1 waiting, p2 on bed-3 with
oxygen `o2_1`, nurse1 busy, doc2 assigned) so the oxygen and summary commands are demoable in any
order. `ensure_seeded()` is self-healing: it reads live index sets back and re-seeds once if core
inventory is missing; the boot banner prints the counts so a partial/failed seed is loud, not silent.

---

## 3. The OrchestratorAgent (the only public surface)

[`er_twin/agents/orchestrator.py`](er_twin/agents/orchestrator.py). The only agent with a mailbox and
the Chat Protocol (`Protocol(spec=chat_protocol_spec)` — there is no importable `chat_proto`).

**Chat lifecycle (`ORCH-CHAT-002`):**

1. `ChatMessage` arrives → **acknowledge immediately** (`ChatAcknowledgement`).
2. **Strip the ASI:One mention** — ASI:One prepends `@agent1…` for routing; `strip_agent_mention()`
   removes it so downstream lookups see the operator's actual words.
3. **Resolve intent** (`resolve_command`): under `USE_MOCK` use the deterministic keyword lookup
   (`resolve_intent` over `_INTENT_KEYWORDS`, `ORCH-LLM-003`); otherwise call ASI:One
   (`_resolve_via_llm`, OpenAI-compatible `asi1-mini`, **8 s timeout + `max_retries=0`**) and
   **fall back to the keyword lookup on any error** (`ORCH-LLM-002`) — fast, never hangs. Runs
   off the event loop via `asyncio.to_thread`.
4. **Serialize** (`ORCH-SYS-003`): a `CommandGate` runs one command at a time; while busy, new
   commands are FIFO-enqueued and the user gets "I'm finishing the current ER action." A 30 s
   watchdog (`COMMAND_TIMEOUT_SECONDS`) releases the gate if a reply never lands.
5. **Dispatch** on intent: `ping` · `intake` · `oxygen` · `summary` · `unknown`.

Async replies are correlated back to the right chat session via a `SessionSenders` map and, for
multi-hop flows, by `flow_id`.

---

## 4. The three events

| Event | Chat path | Dashboard path |
|---|---|---|
| **Intake** | Multi-hop async uAgent pipeline | `commit_full_intake` on confirm |
| **Oxygen** | Multi-hop async uAgent pipeline | — (chat / scripted trigger only) |
| **Summary** | Synchronous read of the store | `GET /api/state` (same store) |
| **Discharge / resolve** | PatientDischarge then Bed/Staff release messages | `commit_discharge` / `release_patient_resources` |

### Event 1 — Patient intake (async multi-hop)

Orchestrated by `_start_intake_flow` / `_on_*_response` handlers in `orchestrator.py`, with per-flow
state in [`er_twin/intake_flow.py`](er_twin/intake_flow.py) (`IntakeFlow` dataclass keyed by
`flow_id`):

```
Orchestrator ──PatientIntakeRequest──► AdmissionsAgent
                                           (intake + MRN mint)
             ◄──PatientIntakeResponse──

Orchestrator ──PatientBindRequest───► PatientAgent (bind pooled slot)
             ◄──PatientBindResponse──

Orchestrator ──TriageRequest────────► TriageAgent  (chief_complaint → acuity + specialty)
             ◄──TriageResponse──────

Orchestrator ──BedAssignRequest─────► BedAgent     (assign patient)
             ◄──BedAssignResponse───

Orchestrator ──StaffAssignRequest───► NurseAgent   (assign nurse)
             ◄──StaffAssignResponse─

Orchestrator ──StaffAssignRequest───► DoctorAgent  (page doctor, acuity ≤ 2 only)
             ◄──StaffAssignResponse─

Orchestrator ─── _finish_intake ─── reply to chat
```

Each hop is a separate `@on_message` handler. Duplicate / late responses are no-ops
(`flow_id` gate). The `EHR` module resolves MRNs against `fixtures/ehr_master.json` (read-only);
new patients are registered in-memory for the current runtime (never written to disk).

Dashboard confirm of an `intake_proposal` skips this pipeline and calls `commit_full_intake`,
which runs the same `admissions.intake` / `bind_slot` / `triage` / `assign_*` helpers.

### Event 2 — Low-oxygen alert (async, the showcase)

Genuine fire-and-forget uAgent messaging correlated by `flow_id` (`OxygenFlow` dataclass):

```
chat "oxygen" → SimulateOxygenDropRequest → EquipmentAgent
   EquipmentAgent lowers supply_level + patient SpO₂, then AUTONOMOUSLY emits LowSupplyAlert
on_low_supply  → idempotency gate (in_flight_o2_dispatches, OXY-IDEM-001) → EquipmentLocateRequest
on_locate      → pick replacement unit → StaffDispatchRequest → NurseAgent
on_dispatch    → NurseAgent accepts → apply_oxygen_swap (equipment.swap + nurse.dispatch)
               → confirm to chat, export incident, release gate
```

Duplicate/late responses are no-ops (`flow.status == "done"` guard). Overlapping alerts never
clobber each other because `OxygenFlow` context is keyed by `flow_id`.

### Event 3 — Status summary (read-only)

`build_status_summary(store, alert_beds)` is a pure, store-derived template: active patients, bed
occupancy, free/busy nurses, active O₂ alerts, most-urgent patient. It mutates nothing. Under live
Iris memory it folds in recalled facts (`MEM-FLOW-002`).

---

## 5. Discharge and resolve flows

Like intake, **chat** discharge and resource release are async uAgent pipelines correlated by
`flow_id` ([`er_twin/discharge_coord.py`](er_twin/discharge_coord.py)). Dashboard confirm/resolve
call `commit_discharge` / `release_patient_resources` on the same store.

```
DischargeFlow: Orchestrator ──PatientDischargeRequest──► PatientAgent
                             ◄──PatientDischargeResponse─

ResolveFlow:   Orchestrator ──BedReleaseRequest─────────► BedAgent
                             ◄──BedReleaseResponse─────
               Orchestrator ──StaffReleaseRequest────────► NurseAgent / DoctorAgent
                             ◄──StaffReleaseResponse────
```

Resources are released in parallel where possible (bed + nurse + doctor queued together, drained
as responses arrive). Active events are **deleted** from the store on resolution (not just marked
resolved) so `list_active_events` and `list_ids` never accumulate stale entries.

---

## 6. Messaging model

- **Async, not request/response** — all `ctx.send` calls are fire-and-forget; replies arrive in
  separate `@on_message` handlers and are correlated by `flow_id` or the session sender map.
- **Shared message models** live in [`er_twin/protocols.py`](er_twin/protocols.py) as uAgent
  `Model` classes in request/response pairs: `PingRequest/Response`, `PatientIntake*`,
  `PatientBind*`, `Triage*`, `BedAssign*`, `StaffAssign*`, `PatientDischarge*`, `BedRelease*`,
  `StaffRelease*`, `LowSupplyAlert`, `EquipmentLocate*`, `StaffDispatch*`,
  `SimulateOxygenDropRequest`.
- **Chat Protocol** (`uagents_core.contrib.protocols.chat`): `ChatMessage`,
  `ChatAcknowledgement`, `TextContent`, `EndSessionContent` — Orchestrator only.
- **CommandGate** — serializes concurrent chat commands into a FIFO queue; one command is active
  at a time. The gate is released by `_complete_command` (called from the final `@on_message`
  handler of each flow, not from the command entry point).

---

## 7. State & memory

### Storage ([`er_twin/storage.py`](er_twin/storage.py))

`StorageInterface`: `get / set / update / delete / list_ids / publish`. Agents depend only on this
interface — no concrete backend imports.

- **`InMemoryStore`** — process-local dict; zero dependencies; the `USE_MOCK` default. All tests
  run against `InMemoryStore`.
- **`RedisStore`** — hashes keyed `er:{entity}:{id}`; index sets `er:index:{entity}` (so
  `list_ids` never needs `KEYS`/`SCAN`); event feed `er:events` as a **Redis Stream** (`XADD`,
  allowing the dashboard to replay history via `XRANGE`/`XREVRANGE`). **Writes are atomic** —
  `pipeline(transaction=True)` wraps `DEL+HSET+SADD` (set) / `HSET+SADD` (update) / `DEL+SREM`
  (delete) to prevent partial writes under a network stall.
- `make_store()` selects the backend from `USE_MOCK` + `REDIS_URL`.

### Memory ([`er_twin/memory.py`](er_twin/memory.py))

`MemoryInterface`: `record_event / recall / close`. `IrisMemory` (Redis Agent Memory / Iris —
appends session events with UTC timestamps, semantic long-term recall) vs `NoopMemory` (silent,
the default). `make_memory()` selects by `USE_MOCK` + `AGENT_MEMORY_*`. Recording/recall is
**best-effort and non-fatal** (`MEM-FLOW-001/002`, `MEM-ERR-001`) — a memory failure never aborts
a live command. `close()` is called on Bureau shutdown to release connections cleanly.

### EHR ([`er_twin/ehr.py`](er_twin/ehr.py), `fixtures/ehr_master.json`)

Master patient chart keyed by **MRN** (person-scoped, stable across visits) — distinct from
`patient_id` (visit-scoped). Intake resolves an MRN (or mints one for a walk-in) and loads history
(meds/conditions/allergies). The fixture file is **read-only**; new patients registered at runtime
are stored in a module-level in-memory dictionary (`_runtime_new_patients`) and never written to
disk.

---

## 8. Replay

Deterministic milestone capture → on-disk artifacts — driven by
[`er_twin/replay.py`](er_twin/replay.py):

- **`ReplayRecorder`** — one per process; a monotonic `seq` counter (no wall-clock in the event
  line, so runs are reproducible, `REPLAY-LOG-002`) and per-type incident counters. Each milestone
  publishes a structured line to `er:events` **and** captures a full-state snapshot (real `ts`,
  keyed by `seq`, `REPLAY-SNAP-001`).
- **On completion**, `export_incident_timeline` writes a timeline
  `out/replay/{incident_id}.json` with all ordered snapshots. Nothing is written if there were no
  milestones.
- **`/replay/{incident_id}`** page replays the timeline on the same SVG floor map as the live
  dashboard (shared `floor.js`), tweening tokens between snapshots in real time.
- **`/library`** page (auth-gated) lists every incident recorded this session.

---

## 9. Dashboard ([`dashboard/`](dashboard/))

FastAPI app co-hosted on the same event loop as the Bureau. Endpoints:

| Endpoint | Auth | Description |
|---|---|---|
| `GET /api/state` | ✅ | Live ER snapshot (all entity lists + derived KPIs) |
| `GET /api/events` | ✅ | Recent `er:events` lines |
| `GET /api/active_events` | ✅ | Unresolved current events awaiting admin action |
| `POST /api/active_events/{id}/confirm` | ✅ | Direct-store confirm (`commit_full_intake` / `commit_discharge`) |
| `POST /api/active_events/{id}/resolve` | ✅ | Archive, delete, and (for discharge) `release_patient_resources` |
| `POST /api/command` | ✅ | Always `403` — commands go through Orchestrator chat |
| `GET /api/replay/{id}` | public | Timeline JSON for the replay page |
| `GET /api/library` | ✅ | Index of recorded incidents |

Auth: form-based session cookie (`username` / `password` from config) or Google OAuth (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`). An optional `GOOGLE_ALLOWED_EMAILS` list restricts OAuth to named addresses.

**Data source** (`DASHBOARD_SOURCE`):
- `live` (default) — the shared in-process `InMemoryStore` injected by `main.py`.
- `redis` — a separate `RedisStore` connection; used when the dashboard runs standalone against a shared Redis instance.
- `fixture` — loads `fixtures/` JSON; used by unit tests.

---

## 10. Configuration

[`er_twin/config.py`](er_twin/config.py) (`pydantic-settings`, `.env`):

| Setting | Default | Effect |
|---|---|---|
| `USE_MOCK` | `true` | `true` → InMemoryStore + NoopMemory, deterministic, no external calls |
| `AGENT_SEED` | `er-twin-demo-seed` | derives every agent address (don't change → preserves the mailbox) |
| `REDIS_URL` | `""` | set + `USE_MOCK=false` → RedisStore |
| `AGENT_MEMORY_*` | `""` | set + `USE_MOCK=false` → IrisMemory |
| `DASHBOARD_SOURCE` | `live` | datasource for the dashboard |
| `DASHBOARD_PORT` | `8050` | uvicorn port for the co-hosted dashboard |
| `GOOGLE_ALLOWED_EMAILS` | `""` | comma-separated email allowlist for OAuth (empty = any authenticated email) |

`network="testnet"` is hardcoded on every agent to quiet Almanac warnings.

```bash
USE_MOCK=true uv run python -m er_twin.main          # demo-safe, no external deps
uv run python -m er_twin.main --connect-mailbox       # one-time mailbox bootstrap
uv run pytest                                         # full test suite
```

---

## 11. Key invariants (traced to EARS specs)

- `DOMAIN-STATE-001/002/003` — a bed holds ≤1 patient; a patient holds ≤1 bed; a discharged
  patient can't be triaged without a new intake.
- `INTAKE-IDEM-001/002`, `OXY-IDEM-001` — intake dedupes by MRN/name; bed/nurse/doctor assignment
  and the oxygen swap are idempotent; duplicate oxygen alerts for the same unit are ignored.
- `ORCH-SYS-003` — exactly one chat command in flight at a time.
- Capacity: 3 patient slots, 4 beds, 2 nurses (1 patient each), 2 doctors (load cap 3), small
  equipment pool — kept small so a local run is deterministic.

Code and tests carry `# @spec <ID>` comments tracing back to these specs.
