# STATUS — ER Twin

Live progress tracker. Update as phases complete. See
[implementation plan](docs/plans/2026-06-20-er-twin-core.plan.md) for detail.

**Current blocker:** _none — Phases 0–5 + R + P all landed (69/69 tests pass; `ruff check .` clean). Phase P (Pika MCP automation) scripts written + parse-verified: `scripts/run_pika_identity_check.ps1` (smoke test, fails on non-empty `permission_denials`), `scripts/run_pika_replay.ps1` (brief → CLI w/ explicit `--allowedTools` + `task_status` → `out/pika_result.json`, prints media URL/`task_id`), and `scripts/pika_replay_operator.md` (Alt A automated + Alt B manual VSCode fallback). Pika has no EARS specs by locked decision; the CLI contract lives in LLD §9 + the plan (user-confirmed: proceed on LLD §9). REMAINING = operator action only: run the scripts pre-demo (needs the Claude CLI on PATH + Pika auth; spends credits) and pre-generate the final replay._
**Agents-layer focus (Evan):** Demo readiness — operator pre-flight (`run_pika_*.ps1`) + rehearse the 3 trigger phrases. All build phases (0–5, R, P) DONE; Phase 6 RedisStore + dashboard are other owners. Phases 0–3 DONE: skeleton + entity agents/invariants + patient intake. **Transport decided (hybrid — [decision](docs/decisions/2026-06-20-intake-orchestration-mode.md)):** intake stays in-process/`INTAKE_MODE=direct` (canonical + demo-safe); Phase 4 oxygen is the **mandatory** real-async-messaging showcase; async intake is optional (behind `INTAKE_MODE=async`) only if time allows.
**Env:** venv pinned to Python 3.12 (3.14 broke `uagents==0.25.2`); pin `requires-python = ">=3.11,<3.13"` in Phase 1.
**Pika MCP:** ✅ installed (project-scope [.mcp.json](.mcp.json)), authenticated, 5k credits. Headless CLI path verified (needs explicit `--allowedTools`). Automation scripts = Phase P.

## Phases

| Phase | Description | Owner | Status |
|---|---|---|---|
| 0 | Scaffold & contracts (`protocols`, `config`, `storage`, `addresses`) | Evan | **complete** |
| 1 | Single-process Bureau skeleton — Orchestrator + stub in one Bureau (`main.py`), in-process chat ping, `USE_MOCK` — **P1+P2** | **Evan** | **complete** |
| 2 | Entity agents + state + domain invariants | **Evan** | **complete** |
| 3 | Event 1 — Patient intake — **P3** | **Evan** | **complete** |
| 4 | Event 2 — Low oxygen alert (mandatory real-async-messaging showcase) | **Evan** | **complete** |
| 5 | Event 3 — Status summary | **Evan** | **complete** |
| R | Incident replay bridge (`er:events` log → `out/*.json` + `pika_prompt.md`) — **P4** | **Evan** | **complete** |
| P | Pika MCP automation (`run_pika_*.ps1` → Claude Code CLI → `out/pika_result.json`) — **P5** | **Evan** | **scripts done** (operator pre-flight pending) |
| 6 | Redis swap (`RedisStore`), demo scripting — **P6** | redis dev | not started |
| Stretch | Dashboard (FastAPI + HTML) — **P7** | dashboard dev | not started |
| Stretch | fal.ai fallback (only if Pika MCP fails / time remains) — **P7** | **Evan** | not started |

## Agents layer — Evan's critical path

The detailed checklist for my owned phases. Mirrors the
[implementation plan](docs/plans/2026-06-20-er-twin-core.plan.md); check items off here as they land.
Each handler/test must carry `# @spec <ID>` per the plan's TDD agreement.

### Phase 1 — Single-process Bureau skeleton `ORCH-*`

- [x] `er_twin/agents/orchestrator.py` — mailbox + chat `Protocol(spec=chat_protocol_spec)` (constructed, not imported), intent resolution (ASI:One / `USE_MOCK`), session→sender correlation map, ping dispatch
- [x] `er_twin/agents/stub.py` — `PingRequest` → `PingResponse`
- [x] `er_twin/main.py` — single entry: ONE `Bureau`, add Orchestrator (`mailbox=True`, `publish_agent_details=True`, `network="testnet"`) + stub, `bureau.run()`
- [x] `pyproject.toml` — pin `requires-python = ">=3.11,<3.13"` (3.14 breaks `uagents==0.25.2`)
- [x] `tests/test_orchestrator_skeleton.py` — `ORCH-SKEL-001`, `ORCH-LLM-002/003/004`, `ORCH-SYS-003` (11 tests green; ASI:One LLM call `ORCH-LLM-001` deferred to Phase 5)
- [x] Boot verified: `USE_MOCK=true uv run python -m er_twin.main` → both agents in one Bureau, "Starting mailbox client" + "Manifest published successfully: AgentChatProtocol"; in-process ping round-trip covered by unit tests (manual ASI:One chat needs the one-time inspector connect)
- [x] `spikes/mailbox_inside_bureau_spike.py` — mailbox-in-Bureau proven (exit 0; mailbox client starts; in-process round-trip)

### Phase 2 — Entity agents & state `DOMAIN-STATE-*`

- [x] `er_twin/agents/patient.py` — pool of N (=3), `bound_to`, `PatientBindRequest` handler; pure `bind_slot`/`find_idle_slot`/`can_triage`
- [x] `er_twin/agents/bed.py` — `assign_patient_to_bed`/`release_bed`, `DOMAIN-STATE-001`+`002` guards (idempotent)
- [x] `er_twin/agents/nurse.py` — availability, assignments, `find_available_nurse`
- [x] `er_twin/agents/doctor.py` — specialty, load, `find_available_doctor`
- [x] `er_twin/agents/equipment.py` — per-type supply/in-use, `is_low_supply`/`is_available` (threshold 50)
- [x] `er_twin/main.py` UPDATE — shared `InMemoryStore`, `seed_state`, all 16 agents in one Bureau (boot verified)
- [x] `tests/test_domain_invariants.py` — `DOMAIN-STATE-001/002/003`
- [x] `tests/test_patient_pool.py` — `INTAKE-BIND-002` (+ `003` pool-exhaustion detection; Orchestrator report is Phase 3)

### Phase 3 — Event 1: Patient intake `INTAKE-*`

- [x] `er_twin/agents/admissions.py` — intake record + dedupe (`INTAKE-IDEM-001`), `p{n}` via `er:counter:patient`
- [x] `er_twin/agents/triage.py` — acuity + specialty (`INTAKE-FLOW-004`, `INTAKE-STATE-002`), discharge guard
- [x] `er_twin/agents/orchestrator.py` UPDATE — `run_intake` coordinator + doctor page (`INTAKE-FLOW-010`), `MOCK_INTAKE`, `DISPLAY_NAMES`, status transitions; chat intake intent wired
- [x] `er_twin/agents/{bed,nurse,doctor}.py` UPDATE — `find_available_*` + `assign_*` with capacity (R2-A) + idempotency (`INTAKE-IDEM-002`)
- [x] `er_twin/main.py` UPDATE — `seed_baseline` (R2-B), admissions/triage agents, `orch.set_store`
- [x] `tests/test_event_intake.py` — full flow + all `ERR`/`IDEM` specs (15 tests)
- [x] Verified: chat _"A new patient arrived with chest pain"_ → `run_intake` admits p3 → bed-1 + Nurse Chen; paged Dr. Smith (in-process; 18 agents boot)
- [~] **Transport:** intake fan-out runs in-process over the shared store (not uAgent envelopes). Async-message conversion is an open decision (see decision docs + arrow note)

### Phase 4 — Event 2: Low oxygen alert `OXY-*`

- [x] `er_twin/agents/equipment.py` UPDATE — `SimulateOxygenDropRequest` handler emits autonomous `LowSupplyAlert` (OXY-FLOW-007/001); `EquipmentLocateRequest` handler (OXY-FLOW-003); pure `simulate_oxygen_drop`/`locate_replacement`/`swap_oxygen_unit`
- [x] `er_twin/agents/orchestrator.py` UPDATE — async `on_low_supply`/`on_locate`/`on_dispatch` handlers (alert → locate → dispatch → swap), `in_flight_o2_dispatches` dedupe (`OXY-IDEM-001`), `apply_oxygen_swap`, chat oxygen branch
- [x] `er_twin/agents/nurse.py` UPDATE — `StaffDispatchRequest` handler + pure `dispatch_nurse`
- [x] `tests/test_event_oxygen.py` — flow + no-unit error + idempotency (9 tests; 51 total green)
- [x] Verified: `spikes/oxygen_async_flow_spike.py` drives the real async chain through a live Bureau (exit 0; logs `alert_raised → unit_located → nurse2 accepts → oxygen_swap_complete`). Manual chat _"Bed 3's patient oxygen is dropping"_ available once the Agentverse inspector mailbox is connected

### Phase 5 — Event 3: Status summary `SUMM-*`

- [x] `er_twin/agents/orchestrator.py` UPDATE — pure `build_status_summary` (read-only, store-derived template, decision R2-F) + synchronous summary branch in `_dispatch_command`; empty-ER case; ASI:One LLM path left as the deferred seam. Removed the now-dead `MOCK_REPLIES` fallthrough (kept the dict only as the no-store fallback)
- [x] `tests/test_event_summary.py` — baseline + after-intake template strings, empty-ER (`SUMM-ERR-001`), active-O2-alert line + pluralization, "Most urgent" selection/tie-break, read-only invariant (`SUMM-STATE-001`) — 8 tests; 61 total green
- [x] Boot verified: `USE_MOCK=true uv run python -m er_twin.main` → 18 agents start clean. Manual chat _"Show me what's happening in the ER"_ available once the Agentverse inspector mailbox is connected

### Phase R — Incident replay bridge `REPLAY-*` (P4)

- [x] `er_twin/agents/orchestrator.py` UPDATE — `ReplayRecorder` publishes structured `er:events` milestone lines (`REPLAY-LOG-001/002`); intake publishes `run_intake` milestones, oxygen publishes per async handler into `OxygenFlow.lines`, summary publishes `summary_generated`; `_emit_replay` exports on completion
- [x] `er_twin/replay.py` — `ReplayRecorder` (seq + per-type incident counters), pure `build_brief` (LLD §9 schema; `t` from relative `seq`, severity from acuity), `render_pika_prompt`, `write_incident` (per-incident `out/{incident_id}.json` + latest copy), `export_incident` (`REPLAY-BRIEF-001/003/004`)
- [x] `scripts/build_pika_prompt.py` — standalone re-render of `out/pika_prompt.md` from a brief (synthetic-data/safety + return contract; `REPLAY-BRIEF-002`). `export_incident` also writes the prompt inline during a live run
- [x] `out/.gitkeep` — track `out/`; `.gitignore` switched to `out/*` + `!out/.gitkeep` so generated `*.json`/`*.md` stay ignored
- [x] `tests/test_replay.py` — 8 tests: `REPLAY-LOG-*` (seq ordering, structured lines, no wall-clock), `REPLAY-BRIEF-*` (schema, `incident_type` mapping, no-empty-artifact, prompt safety/return-contract) + a live `run_intake`→export integration. On-disk end-to-end verified (8-milestone intake brief + prompt well-formed)

### Phase P — Pika MCP automation (P5)

- [x] `scripts/run_pika_identity_check.ps1` — CLI identity+balance smoke test; locates CLI (`$env:CLAUDE_CLI` override); fails if `permission_denials` non-empty → `out/pika_identity_check.json`. Parse-verified
- [x] `scripts/run_pika_replay.ps1` — requires `out/incident_replay_brief.json`; regenerates `pika_prompt.md` if missing; CLI (`--mcp-config .mcp.json --allowedTools <pika set + task_status>`) → `out/pika_result.json`; fails on non-empty `permission_denials`; prints media URL/asset ID/`task_id`; no `--dangerously-skip-permissions`. Parse-verified
- [x] `scripts/pika_replay_operator.md` — operator runbook (Alt A automated path + Alt B manual VSCode `/mcp` fallback + troubleshooting table)
- [ ] **Operator action (pre-demo, needs the Claude CLI + Pika auth):** run `run_pika_identity_check.ps1` (expect `permission_denials: []`), then pre-generate the **final** replay from a real brief; keep the live CLI run as proof-of-work. _Not runnable from this dev env (no `claude` on PATH; live run spends Pika credits)._

### Stretch (only if ahead at hour 20)

- [ ] fal.ai fallback — only if Pika MCP fails / time remains (no `er_twin/` code)
- [ ] PharmacyAgent + a 4th event

> **Not mine:** Phase 6 `RedisStore` (redis dev) and the FastAPI dashboard (dashboard dev). I just
> keep the `StorageInterface` and the [TEAM.md mock fixture](docs/TEAM.md) schema stable so they stay unblocked.

## Demo readiness checklist

- [ ] All 3 events fire end-to-end from a single chat command each
- [ ] `USE_MOCK=true` runs the full demo with no external API calls
- [ ] `.env.example` present; no secrets committed
- [ ] Demo trigger phrases rehearsed (see `docs/TEAM.md` USE_MOCK contract)
