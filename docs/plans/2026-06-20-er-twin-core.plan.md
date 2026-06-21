# Implementation Plan — ER Twin Core (2026-06-20)

**Traces to:** [EARS specs](../specs/er-events-specs.md) · [LLD](../llds/er-twin-core.lld.md) · [README/HLD](../../README.md)
**Scope:** the full core system — Bureau + Orchestrator skeleton first, then the 3 demo events.
**Working agreement:** spec-driven + **TDD**. For each behavioral spec: write a failing `pytest` test tagged `# @spec <ID>`, implement to green, refactor. Annotate handlers with `# @spec <ID>`.

**Ownership** (per [TEAM.md](../TEAM.md)): Phases 1–5 + replay bridge (Phase R) + Pika automation (Phase P) → **Evan (agents layer, critical path)**; Phase 6 `RedisStore` → redis dev; dashboard stretch → dashboard dev. Live checklist for the agents layer lives in [STATUS.md](../../STATUS.md#agents-layer--evans-critical-path).

---

## Build Priority Order

Strict priority — start a level only when the previous one demonstrably works. Phases below map to these.

| Priority | Goal | Phase(s) |
|---|---|---|
| **P1 — Mandatory Fetch.ai judging path** | ASI:One → Agentverse mailbox Orchestrator round-trips (Chat Protocol + `USE_MOCK`); deterministic trigger routing | Phase 1 |
| **P2 — Minimal local agent coordination** | Orchestrator → `StubAgent` `PingRequest`/`PingResponse` **in-process** (one Bureau) | Phase 1 |
| **P3 — One meaningful ER event** | Orchestrator dispatches to local agents → they update the store → useful chat reply | Phase 2 (only what the event needs) + Phase 3 *(intake)* |
| **P4 — Incident replay bridge** | Structured event log → `out/incident_replay_brief.json` + `out/pika_prompt.md` | **Phase R** (after the first event works) |
| **P5 — Pika MCP automation** | `run_pika_identity_check.ps1` + `run_pika_replay.ps1` → Claude Code CLI (`--mcp-config .mcp.json --allowedTools`) → `out/pika_result.json` | **Phase P** (after Phase R) |
| **P6 — Redis** | `RedisStore` behind the existing interface; `InMemoryStore` stays default; never blocks P1 | Phase 6 |
| **P7 — Stretch (cut first)** | Remaining events, dashboard, captions/voiceover, fal.ai fallback, PharmacyAgent | Phases 4–5 beyond the first event, Stretch |

> **Fetch-native, single public surface, one process.** No adapter / no other framework in the
> runtime; only the Orchestrator is registered; ASI:One talks to nothing else. The Orchestrator
> (`mailbox=True`) and all private entity agents run in **one `Bureau`, one process** (`main.py`) —
> spike-proven on `uagents==0.25.2`. Pika MCP is invoked by the **Claude Code CLI** — never from
> `er_twin/`. The **two-process** split (standalone Orchestrator + separate Bureau, Alternative G) is
> the documented **fallback** if ASI:One smoke testing fails. fal.ai is an optional, cuttable fallback
> (Alternative E). See README → *Architecture Alternatives and Fallbacks*.

---

## Pattern Grounding

No prior code exists (greenfield). Conventions come from the **RONGERS Standards** in [LLD §RONGERS Standards Applied](../llds/er-twin-core.lld.md#rongers-standards-applied) — mirror those rather than inventing new ones:

| Category | Source pattern |
|---|---|
| Package / module layout | LLD §1 (`er_twin/` single package) |
| Message schemas | LLD §3 — `uagents.Model` request/response pairs in `protocols.py` |
| State access | LLD §4 — `StorageInterface`, `er:{entity}:{id}` keys; in-memory first |
| Config | `pydantic-settings` (`config.py`), `USE_MOCK` flag |
| Addressing | LLD §5 — seed-derived constants in `addresses.py` |
| Errors | LLD §6 — wrap `ctx.send`, graceful chat messages, LLM fallback |
| Tests | `pytest`, `# @spec` annotations, TDD |

---

## Phase 0 — Scaffold & Contracts

**Deliverable:** installable package, settings, storage interface, all message models, address constants. No behavior yet.

| File | Action | Reason |
|---|---|---|
| `pyproject.toml` | CREATE | uv project; deps: `uagents`, `uagents-core`, `pydantic-settings`, `redis`, `pytest`, `ruff` |
| `.env.example` | CREATE | Keys: `ASIONE_API_KEY`, `REDIS_URL`, `FAL_KEY`, `AGENT_SEED`, `USE_MOCK` |
| `er_twin/config.py` | CREATE | `Settings` via pydantic-settings |
| `er_twin/protocols.py` | CREATE | All `Model` classes from LLD §3 (incl. `PatientBind*`, `Ping*`) |
| `er_twin/storage.py` | CREATE | `StorageInterface` + `InMemoryStore` |
| `er_twin/addresses.py` | CREATE | seed-derived address constants |
| `tests/test_storage.py` | CREATE | TDD for `InMemoryStore` get/set/update/list_ids |

- [x] Phase 0 complete — scaffold merged to `main`; `tests/test_storage.py` green (7/7).
- **Validation:** `uv run ruff check . && uv run pytest tests/test_storage.py`

---

## Phase 1 — Single-Process Bureau Skeleton (FIRST SLICE)

**Owner:** Evan (agents)
**Specs:** `ORCH-CHAT-001/002`, `ORCH-SYS-001/002/003`, `ORCH-LLM-001/002/003/004`, `ORCH-SKEL-001`
**Priorities:** P1 (public Orchestrator, mailbox + Chat Protocol) + P2 (in-process Orchestrator → stub ping)
**Deliverable:** one process runs; Orchestrator registered (mailbox + Chat Protocol, `publish_agent_details=True`); a chat ping round-trips **in-process** to a stub agent in the same Bureau; `USE_MOCK` path works. Spike-proven seam.

| File | Action | Reason |
|---|---|---|
| `er_twin/agents/orchestrator.py` | CREATE | mailbox + chat `Protocol(spec=chat_protocol_spec)` (constructed, not imported); intent resolution (ASI:One or `USE_MOCK`); session→sender correlation map; serialization; ping dispatch |
| `er_twin/agents/stub.py` | CREATE | minimal agent handling `PingRequest`→`PingResponse` |
| `er_twin/main.py` | CREATE | single entry: build ONE `Bureau`, `add(orchestrator)` + `add(stub)`, `bureau.run()`. Orchestrator uses `network="testnet"` |
| `tests/test_orchestrator_skeleton.py` | CREATE | `# @spec ORCH-SKEL-001`, `ORCH-LLM-002/003/004`, `ORCH-SYS-003`; unit-test the pure intent resolver + session map (no live Bureau needed) |
| `pyproject.toml` | UPDATE | pin `requires-python = ">=3.11,<3.13"` (3.14 breaks `uagents==0.25.2` event-loop init) |

- [x] Phase 1 complete (**= first-slice Definition of Done in STATUS.md**) — 11 skeleton tests + 7 storage green; `ruff check .` clean; boot verified (mailbox client + `AgentChatProtocol` manifest). `ORCH-LLM-001` (real ASI:One call) deferred to Phase 5.
- **Validation:** `uv run pytest tests/test_orchestrator_skeleton.py` + manual: `USE_MOCK=true uv run python -m er_twin.main`, send a chat ping, observe the in-process stub reply relayed to chat.

> **Async correlation (critical):** uAgent sends are fire-and-forget. The chat handler stores
> `{session/request id → user sender address}`, dispatches `PingRequest`, and returns; the
> `@on_message(PingResponse)` handler looks up the sender and sends the chat reply. Do not write the
> chat handler as if it can synchronously await the stub.
>
> **Fallback (Alternative G, two-process):** if ASI:One/Agentverse smoke testing fails, split into
> `er_twin/run_orchestrator.py` (standalone `orchestrator.run()`, mailbox) + `er_twin/run_bureau.py`
> (`Bureau(endpoint=[...])`) messaged by address. The proven spike is `spikes/mailbox_inside_bureau_spike.py`.

---

## Phase 2 — Entity Agents & State

**Owner:** Evan (agents)
**Specs:** `ORCH-SYS-001`, `DOMAIN-STATE-001/002/003` (guards live in these agents)
**Deliverable:** Patient pool, Bed, Nurse, Doctor, Equipment agents with state read/write; domain invariants enforced.

| File | Action | Reason |
|---|---|---|
| `er_twin/agents/patient.py` | CREATE | pool of N; `bound_to`; `PatientBindRequest` handler |
| `er_twin/agents/bed.py` | CREATE | assignment/release; DOMAIN-STATE-001 guard |
| `er_twin/agents/nurse.py` | CREATE | availability, assignments |
| `er_twin/agents/doctor.py` | CREATE | specialty, load |
| `er_twin/agents/equipment.py` | CREATE | per-type supply/in-use; low-supply check |
| `er_twin/main.py` | UPDATE | instantiate pool + all entity agents |
| `tests/test_domain_invariants.py` | CREATE | `# @spec DOMAIN-STATE-001/002/003` |
| `tests/test_patient_pool.py` | CREATE | `# @spec INTAKE-BIND-002/003` |

- [x] Phase 2 complete — 9 new tests green (DOMAIN-STATE-001/002/003, INTAKE-BIND-002 + pool-exhaustion detection); 27/27 full suite; `ruff` clean; 16 agents boot in one Bureau. `INTAKE-BIND-003` Orchestrator-side report deferred to Phase 3.
- **Validation:** `uv run pytest tests/test_domain_invariants.py tests/test_patient_pool.py`

---

## Phase 3 — Event 1: Patient Intake

**Owner:** Evan (agents)
**Specs:** `INTAKE-FLOW-001..011`, `INTAKE-BIND-001..003`, `INTAKE-STATE-001/002`, `INTAKE-ERR-001..004`, `INTAKE-IDEM-001/002`

| File | Action | Reason |
|---|---|---|
| `er_twin/agents/admissions.py` | CREATE | intake record + dedupe (`INTAKE-IDEM-001`) |
| `er_twin/agents/triage.py` | CREATE | acuity scoring (`INTAKE-FLOW-004`, `INTAKE-STATE-002`) |
| `er_twin/agents/orchestrator.py` | UPDATE | intake orchestration incl. doctor page (`INTAKE-FLOW-010`) |
| `er_twin/agents/{bed,nurse,doctor}.py` | UPDATE | assignment handlers + idempotency (`INTAKE-IDEM-002`) |
| `tests/test_event_intake.py` | CREATE | full flow + all ERR/IDEM specs |

- [x] Phase 3 complete — 15 intake tests green (42/42 full suite); `ruff` clean; 18 agents boot; intake runs end-to-end from chat in-process (`run_intake` → admissions/triage/bed/nurse/doctor). All INTAKE-* `[x]`. **Transport (decision [intake-orchestration-mode](../decisions/2026-06-20-intake-orchestration-mode.md)):** `INTAKE_MODE=direct` is canonical/demo-safe; `INTAKE_MODE=async` is an optional timeboxed enhancement; the mandatory async proof is the Phase 4 oxygen event.
- **Validation:** `uv run pytest tests/test_event_intake.py` + verified chat *"A new patient arrived with chest pain"* → "Admitted Jordan Lee … bed-1 + Nurse Chen; paged Dr. Smith (cardiology)".

---

## Phase 4 — Event 2: Low Oxygen Alert

**Owner:** Evan (agents)
**Specs:** `OXY-FLOW-001..007`, `OXY-ERR-001`, `OXY-IDEM-001`
**Mandatory real-async-messaging showcase** (decision [intake-orchestration-mode](../decisions/2026-06-20-intake-orchestration-mode.md)): EquipmentAgent autonomously emits `LowSupplyAlert`; Orchestrator handles alert → locate → dispatch in separate `@on_message` handlers. This is the Fetch.ai agent-to-agent proof — must be green before any async-intake work.

| File | Action | Reason |
|---|---|---|
| `er_twin/agents/equipment.py` | UPDATE | emit `LowSupplyAlert`; locate handler |
| `er_twin/agents/orchestrator.py` | UPDATE | alert→locate→dispatch; in-flight dedupe (`OXY-IDEM-001`) |
| `er_twin/agents/nurse.py` | UPDATE | `StaffDispatchRequest` handler |
| `tests/test_event_oxygen.py` | CREATE | flow + no-unit error + idempotency |

- [x] Phase 4 complete — 9 oxygen tests green (51/51 full suite); `ruff` clean; 18 agents boot. The event runs as REAL async uAgent messaging: EquipmentAgent autonomously emits `LowSupplyAlert`; Orchestrator `on_low_supply`/`on_locate`/`on_dispatch` handle alert → locate (R2-E) → dispatch → swap (R2-C); `in_flight_o2_dispatches` dedupe (R2-D). All OXY-* `[x]`.
- **Validation:** `uv run pytest tests/test_event_oxygen.py` (pure logic) + `spikes/oxygen_async_flow_spike.py` proves the agent-to-agent chain through a live Bureau (exit 0; `alert_raised → unit_located → nurse2 accepts → oxygen_swap_complete`). Manual chat *"Bed 3's patient oxygen is dropping"* once the Agentverse inspector mailbox is connected.

---

## Phase 5 — Event 3: Status Summary

**Owner:** Evan (agents)
**Specs:** `SUMM-FLOW-001/002`, `SUMM-ERR-001`, `SUMM-STATE-001`

| File | Action | Reason |
|---|---|---|
| `er_twin/agents/orchestrator.py` | UPDATE | pure `build_status_summary` (read-only, store-derived template, R2-F) + synchronous summary branch; empty-ER case; ASI:One LLM left as deferred seam |
| `tests/test_event_summary.py` | CREATE | summary content, empty-ER, read-only invariant |

- [x] Phase 5 complete — 8 summary tests green (61 total); `ruff check .` clean; boot verified (18 agents). Summary is read-only + synchronous (no async messaging, no mutation — LLD §7); removed the now-dead `MOCK_REPLIES` summary fallthrough (kept the dict as the no-store fallback).
- **Validation:** `uv run pytest tests/test_event_summary.py` + manual: chat *"Show me what's happening in the ER"*.

---

## Phase R — Incident Replay Bridge (P3)

**Owner:** Evan (agents)
**Specs:** `REPLAY-LOG-001/002`, `REPLAY-BRIEF-001/002/003`
**Deliverable:** every event appends structured lines to `er:events`; after an event completes the system exports `out/incident_replay_brief.json` + `out/pika_prompt.md`. Start once the first event (Phase 3) works end-to-end.
**Boundary:** the Fetch runtime stops at the files. Pika MCP media generation is automated by the Claude Code CLI in **Phase P**. No Pika/fal.ai code in `er_twin/`.

| File | Action | Reason |
|---|---|---|
| `er_twin/agents/orchestrator.py` | UPDATE | `publish()` structured event-log lines during each event (`REPLAY-LOG-001/002`) |
| `er_twin/replay.py` | CREATE | read `er:events` → write `out/incident_replay_brief.json` (rich schema, LLD §9; `REPLAY-BRIEF-001/003/004`) |
| `scripts/build_pika_prompt.py` | CREATE | render `out/pika_prompt.md` from the brief with the synthetic-data/safety + return-contract instructions (`REPLAY-BRIEF-002`) |
| `out/.gitkeep` | CREATE | keep `out/` in the repo; generated `*.json`/`*.md` inside stay gitignored |
| `tests/test_replay.py` | CREATE | `# @spec REPLAY-LOG-*`, `REPLAY-BRIEF-*`; assert ordering by `seq`, `incident_type` mapping, no-empty-artifact case |

- [x] Phase R complete — 8 replay tests green (69 total); `ruff check .` clean. `ReplayRecorder` publishes `er:events` milestone lines (monotonic `seq`, no wall-clock); `replay.py` exports per-incident `out/{incident_id}.json` + latest `incident_replay_brief.json` + `pika_prompt.md` (LLD §9, R2-G/R2-H). Intake/oxygen/summary all wired; on-disk end-to-end verified for intake. `scripts/build_pika_prompt.py` re-renders the prompt from a brief.
- **Validation:** `uv run pytest tests/test_replay.py` + on-disk run (intake → `out/incident_replay_brief.json` + `out/pika_prompt.md`, both well-formed). Live chat run needs the one-time Agentverse inspector connect.

---

## Phase P — Pika MCP Automation (P5)

**Owner:** Evan (agents)
**Specs:** none (external post-processing — out of EARS scope; contract in LLD §9).
**Deliverable:** the verified headless Claude-Code-CLI → Pika MCP path, scripted. Start once Phase R writes a valid brief.
**Boundary:** scripts only; no `er_twin/` code calls Pika. Primary = Alternative A; manual VSCode = Alternative B fallback.

| File | Action | Reason |
|---|---|---|
| `scripts/run_pika_identity_check.ps1` | CREATE | locate bundled Claude CLI (env-var overridable); run `--mcp-config .mcp.json --allowedTools "mcp__pika-mcp__identity_whoami,mcp__pika-mcp__identity_balance" --output-format json`; write `out/pika_identity_check.json`; **fail if `permission_denials` non-empty** |
| `scripts/run_pika_replay.ps1` | CREATE | require `out/incident_replay_brief.json`; generate/read `out/pika_prompt.md`; call CLI non-interactively with `.mcp.json` + explicit `--allowedTools`; write `out/pika_result.json`; check `permission_denials` empty; print media URL/asset ID/`task_id` or clear error; include `task_status` in allowlist; **avoid `--dangerously-skip-permissions`** |
| `scripts/pika_replay_operator.md` | CREATE | operator runbook: automated path + manual VSCode `/mcp` fallback (Alternative B) |

**Recommended first allowlist:** `identity_whoami`, `identity_balance`, `estimate_cost`, `generate_image`, `generate_video`, `generate_keyframes_video`, `add_captions`, `edit_text_overlay`, `task_status` (all `mcp__pika-mcp__*`).

**First media target:** short 15–25s incident-replay video; backup = cinematic still. Keep it to one simple generation path; **pre-generate the final replay before judging** and use the live run as proof-of-work.

- [x] Phase P scripts complete — `run_pika_identity_check.ps1`, `run_pika_replay.ps1`, `pika_replay_operator.md` written + PowerShell-parse-verified, implementing the LLD §9 invocation contract (explicit `--allowedTools`, `permission_denials` fail-fast, `task_status` in the replay allowlist, no `--dangerously-skip-permissions`, `$env:CLAUDE_CLI` override). No EARS specs (locked decision: Pika is out of EARS scope; contract lives in LLD §9 + this plan).
- [ ] **Operator pre-flight (not automatable from the dev env):** needs the Claude CLI on PATH + Pika auth; the live run spends credits. Run the identity check, then pre-generate the final replay before judging.
- **Validation:** `pwsh scripts/run_pika_identity_check.ps1` → `out/pika_identity_check.json` with `permission_denials: []` and balance; then `pwsh scripts/run_pika_replay.ps1` from a real brief → `out/pika_result.json` with a media URL/asset ID/`task_id`.

---

## Phase 6 — Redis Swap, Polish, Demo Scripting

**Owner:** redis dev (not Evan) — Evan keeps `StorageInterface` stable so this stays unblocked.
**Deliverable:** real Redis; deterministic scripted demo; full suite green.

| File | Action | Reason |
|---|---|---|
| `er_twin/storage.py` | UPDATE | add `RedisStore` (same interface) |
| `er_twin/config.py` | UPDATE | select store by `REDIS_URL` presence |
| `scripts/demo.md` | CREATE | exact trigger phrases for the 3 events |
| `tests/test_storage.py` | UPDATE | run interface contract against `RedisStore` |

- [ ] Phase 6 complete
- **Validation:** `uv run ruff check . && uv run pytest` (full suite) with `REDIS_URL` set.

---

## Stretch (only if ahead at hour 20)

- [ ] FastAPI + HTML dashboard reading `er:events` — *dashboard dev*
- [ ] fal.ai fallback for media generation — **only if Pika MCP fails or time remains** (no `er_twin/` code; optional) — *Evan (agents)*
- [ ] PharmacyAgent + a 4th event — *Evan (agents)*

> The Pika MCP replay itself is **not** stretch — its inputs (`incident_replay_brief.json` +
> `pika_prompt.md`) are produced in **Phase R (P4)** and the automated CLI replay is **Phase P (P5)**
> (`scripts/run_pika_replay.ps1`). fal.ai above is only its fallback (Alternative E).

---

## Definition of Done

- [ ] All non-`[D]` EARS specs implemented and annotated `# @spec` in code + tests
- [ ] `uv run ruff check .` clean
- [ ] `uv run pytest` green (full suite), including every `ERR` and `IDEM` spec
- [ ] All 3 events fire end-to-end from a single hardcoded chat command each (deterministic)
- [ ] `USE_MOCK=true` runs the full demo with no external API calls
- [ ] `.env.example` present; no secrets committed
- [ ] STATUS.md updated to reflect completion; this plan moved to `docs/plans/old/`

---

## Testing Requirements

- Every `FLOW` spec → at least one happy-path test.
- Every `ERR` spec → a test exercising the failure branch.
- Every `IDEM` spec → a "fire the same trigger twice" test asserting no duplicate state.
- Every `DOMAIN` invariant → a guard test asserting the violation is rejected.
- `REPLAY` specs → assert event-log lines are ordered by `seq`, the brief/prompt files are written after an event, and no artifacts are written when no event has run.
- All test functions carry `# @spec <ID>` for traceability.
