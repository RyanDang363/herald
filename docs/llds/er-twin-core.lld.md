# LLD — ER Twin Core (Bureau, Orchestrator, Contracts)

**Component:** Core agent system — Bureau wiring, OrchestratorAgent, shared message protocols, and Redis state contracts.
**HLD reference:** [README.md](../../README.md) (the High-Level Design).
**Event-flow decisions:** [Round 1](../decisions/2026-06-20-event-flow-decisions.md) (intake/oxygen/summary/replay mechanics; Gaps 1–9) · [Round 2](../decisions/2026-06-20-round-2-event-mechanics.md) (staff capacity, oxygen swap, in-flight dispatch, summary defs, replay granularity/brief output).
**Status:** Draft — awaiting review.
**Scope of this LLD:** the shared vocabulary (message schemas + Redis keys) for the whole core system, plus the design of the first slice (Bureau + Orchestrator skeleton). The 3 demo events are covered at the contract level here; their behavioral requirements are specified in EARS (next phase).

---

## RONGERS Standards Applied

These govern every downstream decision in this LLD and the implementation plan.

- **Fetch.ai-native runtime.** Build directly on `uagents` — **no** LangChain/CrewAI/AutoGen and **no** uAgent Adapter in the main runtime. ASI:One talks to **only** the public `OrchestratorAgent`; every other agent is local/private in the Bureau.
- **Pika MCP is post-processing, not runtime.** The Fetch agents emit an incident trace; **Claude Code (MCP host) → Pika MCP** turns it into replay media. uAgents never call Pika or fal.ai directly. fal.ai is an optional/cuttable fallback only.
- **Python 3.11+**; `uagents` + `uagents-core`. Bureau for all internal agents; Chat Protocol only on the Orchestrator.
- **Package layout:** single `er_twin/` package — `agents/`, `protocols.py`, `storage.py`, `config.py`, `main.py`.
- **Message models:** uAgent `Model` subclasses in shared `protocols.py`, named request/response (`XxxRequest` / `XxxResponse`).
- **State:** Redis hashes keyed `er:{entity}:{id}`, behind a `StorageInterface`; in-memory dict implementation first.
- **Config:** `pydantic-settings` over `.env`; `USE_MOCK` flag for hardcoded Orchestrator responses.
- **Addresses:** deterministic seed-derived addresses set as startup constants — no runtime discovery.
- **Tooling:** `uv`, `ruff`, `pytest`. **TDD** for handlers and event flows.

---

## 1. Module Layout

```
er_twin/
├── __init__.py
├── config.py          # Settings (pydantic-settings): API keys, REDIS_URL, USE_MOCK, AGENT_SEED
├── protocols.py       # ALL uAgent Model message schemas (shared vocabulary)
├── storage.py         # StorageInterface + InMemoryStore + (later) RedisStore
├── addresses.py       # Seed-derived agent address constants, computed at startup
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py   # OrchestratorAgent: mailbox + Chat Protocol + ASI:One reasoning
│   ├── admissions.py     # AdmissionsAgent
│   ├── triage.py         # TriageAgent
│   ├── patient.py        # PatientAgent (pool of N, created at startup, bound at intake)
│   ├── nurse.py          # NurseAgent (xN)
│   ├── doctor.py         # DoctorAgent (xN)
│   ├── bed.py            # BedAgent (xN)
│   └── equipment.py      # EquipmentAgent (xN)
├── replay.py          # Incident-trace export: er:events -> out/incident_replay_brief.json + out/pika_prompt.md
└── main.py            # Single entry: build ONE Bureau with Orchestrator (mailbox) + all entity agents; bureau.run()

scripts/
├── build_pika_prompt.py          # (P5) render out/pika_prompt.md from out/incident_replay_brief.json
├── run_pika_identity_check.ps1   # (P5) CLI identity+balance smoke test; fail if permission_denials
├── run_pika_replay.ps1           # (P5) CLI -> Pika MCP replay; write out/pika_result.json
└── pika_replay_operator.md       # (P5) operator runbook: automated path + manual fallback (Alt B)

spikes/
└── mailbox_inside_bureau_spike.py # (Alt F) probe single-process mailbox-inside-Bureau

out/                   # generated artifacts; out/.gitkeep tracked, *.json/*.md gitignored:
                       #   incident_replay_brief.json, pika_prompt.md, pika_result.json, pika_identity_check.json
```

> **Single-process default (spike-proven).** `main.py` builds ONE `Bureau` containing the public
> Orchestrator (`mailbox=True`) and all private entity agents; they communicate **in-process**.
> `spikes/mailbox_inside_bureau_spike.py` proves on `uagents==0.25.2` that the Bureau starts the
> Orchestrator's mailbox client and that in-process messaging round-trips. The **two-process** split
> (standalone Orchestrator + separate `Bureau(endpoint=[...])`) is the documented **fallback** only,
> used if ASI:One/Agentverse smoke testing fails. See README → *Architecture Alternatives and Fallbacks*.

---

## 2. Data Models (entity state)

Stored in Redis as one hash per entity. Field types are the canonical in-memory shape; Redis stores stringified values.

### Patient Agent Pool

PatientAgents are **pre-instantiated at Bureau startup** as a fixed idle pool (N = 3 for the demo) — never spawned at runtime, to preserve deterministic addressing and demo reliability (see §7). On intake the Orchestrator/Admissions **binds** an incoming patient to the next idle PatientAgent and hydrates it with the record. The bound agent then "owns" that patient — it holds the `patient_id`, can update its own vitals, and can autonomously emit deterioration events (relevant to Event 2). On discharge the agent returns to `idle` (state overwritten on next bind); the agent itself is never torn down.

A `PatientAgent` has an internal lifecycle field `bound_to: str|null` (the patient id it currently owns, or `null` when idle). The patient's clinical state lives in the Redis hash below.

### Patient
| Field | Type | Notes |
|---|---|---|
| `id` | str | `p1`, `p2`, … |
| `name` | str | synthetic |
| `chief_complaint` | str | free text from intake |
| `acuity` | int | 1 (most urgent) – 5 (least), ESI scale; set by Triage |
| `specialty` | str | required care specialty (e.g. `cardiology`, `general`); set by Triage (decision Gap 1) |
| `status` | enum | `waiting` \| `in_triage` \| `admitted` \| `in_treatment` \| `discharged`; transitions owned by the Orchestrator (decision Gap 8) |
| `vitals` | dict | canonical keys `{heart_rate, blood_pressure, resp_rate, spo2, temperature_f, pain_score}` (decision R1) |
| `assigned_bed` | str\|null | bed id |
| `care_team` | list[str] | nurse/doctor ids |

### Bed
| Field | Type | Notes |
|---|---|---|
| `id` | str | `bed1`–`bed4` |
| `occupied_by` | str\|null | patient id |
| `status` | enum | `available` \| `occupied` \| `cleaning` |
| `specialty` | str | e.g. `general`, `trauma` |
| `equipment` | list[str] | attached equipment ids |

### Nurse / Doctor
| Field | Type | Notes |
|---|---|---|
| `id` | str | `nurse1`, `doc1`, … |
| `available` | bool | nurse: `False` after one active assignment (`NURSE_CAPACITY=1`); doctor: `False` only at `load >= DOCTOR_LOAD_CAP=3` (decision R2-A) |
| `location` | str | bed/zone id |
| `assignments` | list[str] | patient ids |
| `load` | int | **doctor only** — active patient count; incremented on accept (INTAKE-FLOW-011) |
| `skills` / `specialty` | list[str] / str | nurse skills / doctor specialty |

> **Capacity model (decision R2-A).** Nurse = single active patient (goes `available=False` after one
> assignment; no auto-freeing — there is no discharge event in the demo, decision R2-I). Doctor =
> load-based: accepting a patient increments `load` and stays available while `load < 3`.

### Equipment
| Field | Type | Notes |
|---|---|---|
| `id` | str | `o2_1`, `defib_1`, … |
| `type` | enum | `oxygen` \| `defibrillator` \| `iv_pump` |
| `supply_level` | int\|null | **Per-type:** consumables (`oxygen`) use 0–100%; devices (`defibrillator`, `iv_pump`) leave this `null` and use `in_use_by` for availability. |
| `in_use_by` | str\|null | patient id; the availability signal for devices |
| `location` | str | bed/zone id |
| `needs_restock` | bool (optional) | set `True` on a unit depleted/swapped out (decision R2-C); state-only, no message contract |

> **Availability is type-dependent.** The `EquipmentAgent` checks `supply_level` for consumables (alert when below threshold) and `in_use_by` for devices (free vs occupied). The demo's only equipment event is the oxygen consumable path.

---

## 3. Contracts — Message Schemas (`protocols.py`)

All are `uagents.Model` subclasses. Own-surface resources (this system defines and consumes them all internally). The Orchestrator is the hub: it receives a parsed intent and fans out request/response pairs to entity agents.

### Chat / ASI:One surface (external-facing, Orchestrator only)
Uses the standard `uagents_core.contrib.protocols.chat` `ChatMessage` / `ChatAcknowledgement`. The Orchestrator translates inbound chat text → internal intent via the ASI:One LLM (or `USE_MOCK` lookup).

### Event 1 — Patient Intake
| Message | Direction | Fields |
|---|---|---|
| `PatientIntakeRequest` | Orch → Admissions | `name: str`, `chief_complaint: str`, `vitals: dict` |
| `PatientIntakeResponse` | Admissions → Orch | `patient_id: str`, `record: dict` |
| `PatientBindRequest` | Orch → PatientAgent | `patient_id: str`, `record: dict` *(bind an idle pooled agent + hydrate it)* |
| `PatientBindResponse` | PatientAgent → Orch | `patient_id: str`, `agent_id: str`, `bound: bool` *(`bound=false` if no idle agent)* |
| `TriageRequest` | Orch → Triage | `patient_id: str`, `chief_complaint: str`, `vitals: dict` |
| `TriageResponse` | Triage → Orch | `patient_id: str`, `acuity: int`, `specialty: str = "general"` *(decision Gap 1)* |
| `BedAssignRequest` | Orch → Bed | `patient_id: str`, `required_specialty: str` |
| `BedAssignResponse` | Bed → Orch | `patient_id: str`, `bed_id: str\|null`, `success: bool` |
| `StaffAssignRequest` | Orch → Nurse/Doctor | `patient_id: str`, `bed_id: str` |
| `StaffAssignResponse` | Nurse/Doctor → Orch | `patient_id: str`, `staff_id: str`, `accepted: bool` |

### Event 2 — Low Oxygen Alert
Every oxygen-flow message carries a `flow_id: str` correlation token so the Orchestrator can key the
in-progress flow context by it and survive overlapping/autonomous alerts (see §6). The unit's agent
echoes the `flow_id` it received from `SimulateOxygenDropRequest` into its `LowSupplyAlert`; an
autonomous alert (no simulate trigger) leaves `flow_id` null and the Orchestrator mints one.

| Message | Direction | Fields |
|---|---|---|
| `LowSupplyAlert` | Equipment → Orch | `flow_id: str\|null`, `equipment_id: str`, `type: str`, `supply_level: int`, `location: str` |
| `EquipmentLocateRequest` | Orch → Equipment | `flow_id: str`, `type: str`, `near_location: str` |
| `EquipmentLocateResponse` | Equipment → Orch | `flow_id: str`, `equipment_id: str\|null`, `location: str`, `available: bool` |
| `StaffDispatchRequest` | Orch → Nurse | `flow_id: str`, `task: str`, `target_location: str`, `equipment_id: str` |
| `StaffDispatchResponse` | Nurse → Orch | `flow_id: str`, `staff_id: str`, `accepted: bool`, `eta_note: str` |
| `SimulateOxygenDropRequest` | Orch → Equipment | `flow_id: str`, `bed_id: str`, `equipment_id: str\|null`, `patient_spo2: int = 88`, `new_supply_level: int = 45` *(internal demo trigger — decision Gap 4)* |
| `SimulateOxygenDropResponse` | Equipment → Orch | *(deferred / unused — the EquipmentAgent answers the simulate request by autonomously emitting `LowSupplyAlert`, not a response; kept as historical contract intent from decision Gap 4)* |

> **Event 2 demo trigger (decision Gap 4).** The scripted chat command does not synthesize the alert
> itself. The Orchestrator sends `SimulateOxygenDropRequest` to the EquipmentAgent at the named bed;
> that agent lowers its `supply_level` below threshold (and the bed patient's `spo2`) and **emits the
> `LowSupplyAlert` itself** (OXY-FLOW-001), preserving the autonomous-agent model. The normal
> locate → dispatch flow (OXY-FLOW-002..006) follows unchanged.

### Event 3 — Status Summary
| Message | Direction | Fields |
|---|---|---|
| `StateQueryRequest` | Orch → (any agent) | `entity_type: str` |
| `StateQueryResponse` | agent → Orch | `entity_type: str`, `entities: list[dict]` |

> Note: Status Summary may also read directly from the store (faster, fewer messages). `StateQuery*` exists for the agent-to-agent path; the Orchestrator decides per `USE_MOCK`/performance.

### First-slice skeleton message
| Message | Direction | Fields |
|---|---|---|
| `PingRequest` | Orch → Stub | `text: str` |
| `PingResponse` | Stub → Orch | `text: str`, `agent_id: str` |

---

## 4. Contracts — Redis Key Schema

| Key pattern | Type | Holds | Written by |
|---|---|---|---|
| `er:patient:{id}` | hash | Patient state (§2) | Admissions, Triage, Orch |
| `er:bed:{id}` | hash | Bed state | Bed |
| `er:nurse:{id}` | hash | Nurse state | Nurse |
| `er:doctor:{id}` | hash | Doctor state | Doctor |
| `er:equipment:{id}` | hash | Equipment state | Equipment |
| `er:index:{entity}` | set | all ids of an entity type (e.g. `er:index:patient`) | each agent on init |
| `er:events` | pub/sub channel | JSON event log lines (stretch dashboard feed) | Orchestrator |

`StorageInterface` methods: `get(key) -> dict`, `set(key, dict)`, `update(key, partial_dict)`, `list_ids(entity) -> list[str]`, `publish(channel, msg)`. `InMemoryStore` implements all; `RedisStore` swaps in later with zero handler changes.

---

## 5. Control Flow — First Slice (single-process skeleton)

`main.py` loads `Settings`, computes seed-derived addresses from `addresses.py` constants (deterministic — no runtime discovery), then:

1. Instantiate `OrchestratorAgent` (`mailbox=True`, `publish_agent_details=True`, `network="testnet"`, includes the chat `Protocol(spec=chat_protocol_spec)`) and one `StubAgent` (no mailbox).
2. `bureau = Bureau(); bureau.add(orchestrator); bureau.add(stub); bureau.run()` — ONE process. `Bureau.run_async` starts the Orchestrator's mailbox client (spike-verified).
3. Inbound `ChatMessage` → Orchestrator chat handler → (LLM or `USE_MOCK`) parses intent → stores `{session/request id → user sender address}` → sends `PingRequest` to the stub's address **in-process** → handler returns (no inline reply).
4. Stub's `@on_message(PingRequest)` → replies `PingResponse`. Orchestrator's `@on_message(PingResponse)` → looks up the stored sender → sends the `ChatMessage` reply to the user.

This proves: mailbox registration + Chat Protocol, **in-process** uAgent messaging inside one Bureau, deterministic addressing, the async correlation pattern, and the `USE_MOCK` path — the whole interaction loop in miniature.

> **Async, not request/response.** uAgent sends are fire-and-forget; the reply lands in a separate
> handler (step 4), so the Orchestrator correlates via the stored session→sender map. Do not write
> the chat handler as if it can synchronously await the stub's reply.
>
> If ASI:One/Agentverse smoke testing fails, fall back to the **two-process** layout (standalone
> `orchestrator.run()` + a separate `Bureau(endpoint=[...])` messaged by address). See README →
> *Architecture Alternatives and Fallbacks*.

---

## 6. Error Handling

- Every `ctx.send` wrapped; failures logged via `ctx.logger` and surfaced to the chat as a graceful message, never a crash.
- Orchestrator LLM call has a timeout; on timeout/rate-limit/error → fall back to `USE_MOCK` response so the demo never stalls.
- Bed/staff assignment requests that cannot be satisfied return `success=false`/`accepted=false` (not exceptions); Orchestrator reports "no bed available" to chat.
- Unknown intent from the LLM → Orchestrator returns a clarifying chat message.
- **Idempotency:** state-mutating handlers are no-ops on duplicate input. A second `BedAssignRequest` for a patient already in that bed returns the existing assignment with `success=true` and writes nothing new; a duplicate intake for an already-active patient returns the existing `patient_id` rather than creating a second record (dedupe key: `name` + `chief_complaint` among non-discharged patients).
- **In-flight O2 dispatch (OXY-IDEM-001, decision R2-D):** the Orchestrator holds `in_flight_o2_dispatches: dict[equipment_id, flow_id]` in memory. An entry is added when a dispatch starts and removed only **after** the `StaffDispatchResponse` is accepted, the oxygen-swap state mutation completes, and the chat/replay line is emitted (clear-on-completion, not on-response — state may lag the response). A `LowSupplyAlert` for an `equipment_id` already in the map is ignored (optional note: "O2 dispatch already in progress for {bed}").
- **Flow correlation (multi-hop oxygen):** the oxygen event spans separate `@on_message` handlers (alert → locate → dispatch). uAgents does not carry a session across hops, so the Orchestrator threads a `flow_id` through every oxygen message and keeps per-flow context in `oxygen_flows: dict[flow_id, OxygenFlow]` (bed, depleted/replacement unit, nurse, originating chat session). Each response handler looks up its flow by the message's `flow_id`; a response whose `flow_id` is unknown (already completed / timed out) or whose flow is already `done` is a **no-op** — this makes late/duplicate responses safe and lets overlapping or autonomous alerts coexist without one clobbering another (replaces an earlier single-slot context that was vulnerable to overwrite).
- **Concurrency / serialization (ORCH-SYS-003):** the Orchestrator processes one chat command at a time across its **full lifecycle** — from intent dispatch until that command produces its terminal chat reply — not merely until the first `ctx.send`. An active-command gate holds a single `active_flow_id` (set when a command starts, cleared only in the terminal success/failure/timeout finalizer); commands that arrive while the gate is busy are queued and run when it frees. A per-command watchdog timeout clears the gate (and any oxygen flow) if a reply is lost, so a dropped message can never wedge the Orchestrator. Autonomous alerts (no chat trigger) run their own `flow_id` context but do **not** occupy the chat-command gate.

---

## 7. Decisions & Alternatives

| Decision | Chosen | Alternative considered | Why |
|---|---|---|---|
| State access for Status Summary | Read store directly in Orchestrator | `StateQuery` round-trip to every agent | Fewer messages, faster, demo-safe; query path kept for purity but optional |
| Message style | Request/response `Model` pairs | Past-tense event broadcasts | Orchestrator-hub topology maps cleanly to req/resp; easier to trace and test |
| Equipment alert | Push (`LowSupplyAlert` Equipment→Orch) | Orchestrator polls supply levels | Push matches "agents act" thesis and the demo trigger phrasing |
| Address resolution | Seed-derived constants at startup | Almanac/runtime discovery | Deterministic, no network, demo-reliable (per spec risk mitigation) |
| Patient as agent | Pre-instantiated **pool** of N PatientAgents, bound at intake | (a) record-only, no live agent; (b) dynamic spawn per intake | Pool keeps real PatientAgents (autonomous deterioration for Event 2) while preserving deterministic addressing and demo stability. Dynamic spawn is fragile: runtime Bureau mutation isn't a supported lifecycle, breaks startup-constant addressing, opens a dropped-message timing window, and complicates teardown. |
| Process topology | **Single process**: Orchestrator with `mailbox=True` *inside* one Bureau with the private entity agents | Two processes: standalone Orchestrator + separate `Bureau(endpoint=[...])` (fallback) | Our spike (`spikes/mailbox_inside_bureau_spike.py`) proves the combo works on `uagents==0.25.2` — Bureau starts the mailbox client and in-process messaging round-trips. One process = one event loop, one command, the *proven* seam (vs the two-process *untested* cross-process hop). Two-process is the documented fallback if ASI:One smoke testing fails; multi-process quickstarter style is the last resort. |
| Pika replay boundary | **Automated**: Fetch writes `out/*`; `run_pika_replay.ps1` → Claude Code CLI (`--mcp-config .mcp.json --allowedTools`) → Pika MCP → `out/pika_result.json` | (a) manual VSCode operator (Alt B); (b) uAgents call Pika/fal.ai in-runtime | CLI path verified end-to-end (the only blocker was headless tool-permission denial, fixed by `--allowedTools` — not OAuth). Keeps the Fetch runtime pure; decouples slow/async media from the live path. Manual operator is the live fallback; fal.ai (Alt E) stays optional, never in `er_twin/`. |

---

## 8. Edge Case Resolutions

Resolved with the user before writing EARS. These become explicit specs (incl. idempotency) in the next phase.

| # | Edge case | Resolution |
| --- | --- | --- |
| 1 | No bed available on intake | Leave patient in `waiting`, report to chat. **No auto-retry** when a bed later frees. |
| 2 | No staff accepts assignment | Same — patient stays assigned-to-bed but unstaffed; chat reports "no staff available." No auto-retry. |
| 3 | Duplicate intake | **No-op / dedupe.** Return the existing `patient_id` for an already-active (non-discharged) patient matching `name` + `chief_complaint`; do not create a second record. |
| 4 | Low-oxygen alert, no replacement unit | Report to chat ("no available O₂ unit near {location}"). Do not dispatch a unit that is itself below threshold. |
| 5 | Bed specialty mismatch | Fall back to a `general` bed when no specialty match exists; only report failure if none available at all. |
| 6 | Idempotency of state writes | **No-op on duplicate.** Re-applying the same `BedAssignRequest`/`StaffAssignRequest` returns the existing assignment with `success=true` and writes nothing new. |
| 7 | Equipment supply semantics | **Per-type** — consumables (`oxygen`) use `supply_level` 0–100; devices use `in_use_by`. See §2. |
| 8 | Status Summary with empty ER | Return a graceful "nothing currently happening in the ER" summary, not an error. |
| 9 | Concurrent chat commands | **Serialize** in the Orchestrator — one command fully processed before the next. See §6. |
| 10 | Malformed/partial ASI:One intent | Fall back to `USE_MOCK`/clarifying message (see §6); log the raw LLM output via `ctx.logger` for debugging. |

---

## 9. Incident Replay Bridge (Pika MCP boundary)

The replay layer is **outside the Fetch runtime**. uAgents only produce a structured trace; the
creative step is performed by the **Claude Code CLI → Pika MCP server** (automated, primary path —
Alternative A). This section defines the contract at that boundary (resolves prior open questions on
handoff mechanism and event-line schema).

### Event log line (`er:events` channel)

The Orchestrator `publish()`es one JSON line per significant action via `StorageInterface.publish`.
This is the own-surface contract the replay exporter consumes.

| Field | Type | Notes |
|---|---|---|
| `seq` | int | monotonically increasing within a run (Orchestrator-held counter; no wall-clock dependency) |
| `event` | str | the demo event this line belongs to: `intake` \| `oxygen` \| `summary` |
| `actor` | str | agent id emitting the action, e.g. `orchestrator`, `triage`, `bed1` |
| `action` | str | verb, e.g. `admitted`, `triaged`, `bed_assigned`, `nurse_dispatched` |
| `target` | str\|null | entity acted on (patient/bed/equipment id) |
| `detail` | dict | action-specific payload (acuity, bed_id, supply_level, …) |

> No real timestamps in the trace (`seq` provides ordering) so runs are deterministic and
> reproducible — important for a scripted demo.

**Allocation (decision Gap 9).** The Orchestrator holds `seq` and the incident counters in memory,
reset per process run (no wall-clock, no store dependency):

- `seq` starts at 0 and increments once per published `er:events` line (monotonic per run).
- `incident_counters = {patient_intake, low_oxygen_alert, er_status_summary}` each start at 0; on a
  completed incident, increment its counter and set `incident_id = f"{incident_type}-{n:04d}"`.
- Timeline display: `t = f"00:{seq*5:02d}"` (the demo keeps < 12 lines per incident, so `seq*5 < 60`).

**Milestone granularity (decision R2-G).** Lines are emitted per *milestone*, not per internal
message — success **and** failure milestones:

- **intake:** `intake_received`, `record_created`, `patient_bound`, `triaged`, `bed_assigned`, `nurse_assigned`, `doctor_paged`, `intake_complete`; failures `patient_capacity_reached`, `no_bed_available`, `no_nurse_available`, `no_doctor_available`.
- **oxygen:** `oxygen_drop_simulated`, `alert_raised`, `unit_located`, `nurse_dispatched`, `oxygen_swap_complete`, `oxygen_event_complete`; failures `duplicate_alert_ignored`, `no_replacement_unit_available`, `no_dispatch_nurse_available`.
- **summary:** `summary_generated`.

### `out/incident_replay_brief.json` (own-surface, file handoff)

Written by `replay.py` after an event completes. The handoff is **file-based**: the Fetch process
writes to `out/`, and the Claude Code CLI reads it to drive Pika MCP. The `timeline[].t` field is a
**synthetic display timestamp derived from `seq`** (e.g. `seq*5s`), not wall-clock — runs stay
deterministic. Shape:

```json
{
  "incident_id": "intake-0007",
  "incident_type": "patient_intake | low_oxygen_alert | er_status_summary",
  "title": "Chest-pain intake — ESI-2",
  "summary": "Chest-pain patient admitted to bed-1; nurse-1 + Dr. Smith assigned.",
  "severity": "low | medium | high | critical",
  "location": "ER bed-1",
  "patient": {
    "id": "p1",
    "condition": "synthetic chest pain",
    "acuity": 2
  },
  "timeline": [
    {"t": "00:00", "actor": "AdmissionsAgent", "action": "admitted", "target": "p1", "state_change": "status=waiting"},
    {"t": "00:05", "actor": "TriageAgent", "action": "triaged", "target": "p1", "state_change": "acuity=2"}
  ],
  "final_state": "p1 admitted to bed-1, nurse-1 + Dr. Smith assigned",
  "visual_style": "clean cinematic hospital operations replay",
  "pika_outputs_requested": [
    "15-25 second incident replay video",
    "captioned timeline",
    "voiceover summary"
  ]
}
```

> **Schema note.** This extends the earlier brief shape. The internal `er:events` log line (above)
> keeps `seq`/`detail`; `replay.py` maps each line into a timeline entry, deriving `t` from `seq`
> and `state_change` from `detail`. `incident_type` ∈ {`patient_intake`, `low_oxygen_alert`,
> `er_status_summary`} mirrors the three demo events.

**Field derivation + multi-event output (decision R2-H).**

- `severity` from the incident patient's acuity: `1→critical`, `2→high`, `3→medium`, `4–5→low`. For
  oxygen, use the patient on the affected bed; if none, `severity="medium"` and `patient=null`.
- `visual_style` is a constant per `incident_type` (`patient_intake` → "clean cinematic ER intake and
  triage replay…"; `low_oxygen_alert` → "urgent but non-graphic … rapid oxygen response";
  `er_status_summary` → "clean hospital command-center status visualization").
- **Output:** `replay.py` writes a per-incident history file `out/{incident_id}.json` **and** copies
  the most recent to `out/incident_replay_brief.json` — the fixed path the Phase P Pika script reads.

### `out/pika_prompt.md` (external-consumer contract)

A human-/MCP-readable creative brief derived from the JSON — a scene description Pika MCP can turn
into replay media. Generated by `scripts/build_pika_prompt.py` (or `replay.py`). It must instruct
the model/workflow to:

- use **synthetic hospital data only**; no gore, no identifiable real people, no real PHI;
- create a safe, cinematic, realistic hospital-operations replay;
- emphasize **autonomous coordination** and timeline clarity;
- produce something suitable for a hackathon demo;
- **return** the asset URL/ID, the `task_id` (if async), the tool used, and a short summary.

**First media path — keep it simple:** preferred first target is a **short incident-replay video**
(15–25s) from the brief; backup target is a **cinematic still image**. Do not build a multi-tool
pipeline until one simple generation path works, and **pre-generate the final replay before judging**.

### Automated invocation contract (`scripts/run_pika_replay.ps1` → Claude Code CLI)

**No fal.ai or Pika code ships in `er_twin/`.** The CLI is the bridge:

- requires `out/incident_replay_brief.json`; generates/reads `out/pika_prompt.md`;
- calls the Claude Code CLI non-interactively with `--mcp-config .mcp.json` and an **explicit `--allowedTools`** list (recommended first set: `identity_whoami`, `identity_balance`, `estimate_cost`, `generate_image`, `generate_video`, `generate_keyframes_video`, `add_captions`, `edit_text_overlay`, `task_status`);
- writes raw CLI JSON to `out/pika_result.json`; **fails loudly if `permission_denials` is non-empty**;
- includes `task_status` in the allowlist for long-running jobs; prints the media URL / asset ID / `task_id`, or a clear error if no media result is found;
- **avoids `--dangerously-skip-permissions` by default.**

`scripts/run_pika_identity_check.ps1` is the smoke test: locates the bundled Claude CLI (overridable
via env var), runs `--allowedTools "mcp__pika-mcp__identity_whoami,mcp__pika-mcp__identity_balance"
--output-format json`, writes `out/pika_identity_check.json`, and fails if `permission_denials` is
non-empty. The manual VSCode operator flow (Alternative B) is documented in
`scripts/pika_replay_operator.md` as the live fallback.

---

*Next phase after approval: EARS specs for the 3 events in `docs/specs/`, then the implementation plan in `docs/plans/`.*
