# Arrow: incident-replay

Phase R — the own-surface boundary to Pika MCP (LLD §9). The Fetch runtime never calls Pika: the
Orchestrator publishes one structured JSON line per **milestone** to the `er:events` channel, and
`replay.py` derives `out/{incident_id}.json` + `out/incident_replay_brief.json` + `out/pika_prompt.md`
after each event completes. The Claude Code CLI → Pika MCP step (Phase P) reads those files.

## Status

**OK** — 2026-06-20. Phase R complete and green: 8 replay tests + 61 prior = 69/69 pass,
`ruff check .` clean. All 6 active REPLAY-* specs `[x]`. The full intake chain
(`run_intake` milestones → `er:events` → brief + prompt) was verified **on disk** (8-milestone brief,
correct severity/timeline, safety + return-contract prompt). Oxygen + summary publish paths are wired
into their handlers/branches.

_Mapped + audited in one pass (Phase R landed this session). HLD (README) SHA `8e87478` unchanged
since the other arrows were audited — same upstream._

## References

| Type | Location |
|------|----------|
| HLD — incident replay / demo media | [README.md](../../README.md) |
| LLD — §9 (event-log line, brief schema, prompt contract, invocation boundary) | [docs/llds/er-twin-core.lld.md](../llds/er-twin-core.lld.md) |
| Decisions — Gap 9 (seq/incident counters), R2-G (milestone granularity), R2-H (brief derivation + multi-event output) | [Round 1](../decisions/2026-06-20-event-flow-decisions.md) · [Round 2 §G/§H](../decisions/2026-06-20-round-2-event-mechanics.md) |
| EARS — 6 active REPLAY-* specs | [docs/specs/er-events-specs.md](../specs/er-events-specs.md) |
| Tests | [tests/test_replay.py](../../tests/test_replay.py) (8) |
| Code | [replay.py](../../er_twin/replay.py) (`ReplayRecorder`, `build_brief`, `render_pika_prompt`, `write_incident`, `export_incident`), [orchestrator.py](../../er_twin/agents/orchestrator.py) (`_replay`, `_emit_replay`, milestone `_replay.log` calls in intake/oxygen/summary), [scripts/build_pika_prompt.py](../../scripts/build_pika_prompt.py) |

## Architecture

**Purpose:** Turn each completed ER event into a deterministic, safe creative brief for replay media —
without coupling the Fetch runtime to Pika. The boundary is **files in `out/`**.

**Key Components / flow:**
1. **Milestone log (REPLAY-LOG-001/002):** `ReplayRecorder.log` stamps each milestone with a monotonic
   per-run `seq` and `publish()`es a `{seq, event, actor, action, target, detail}` line to `er:events`.
   No wall-clock field. Intake publishes `run_intake`'s milestone list; oxygen publishes per async
   handler into `OxygenFlow.lines` (alert_raised → unit_located → nurse_dispatched → oxygen_swap_complete
   → oxygen_event_complete, plus failure milestones); summary publishes one `summary_generated` line.
2. **Brief derivation (REPLAY-BRIEF-001/004):** `build_brief` sorts the lines by `seq`, derives
   `severity` from the patient's acuity (R2-H), a synthetic `patient`, `location`, an ordered `timeline`
   (`t` = relative `seq`×5s), and an incident-type narrative. `incident_type` ∈
   {`patient_intake`, `low_oxygen_alert`, `er_status_summary`} via `INCIDENT_TYPES`; `next_incident_id`
   mints `{type}-{n:04d}` from per-type counters.
3. **File handoff (REPLAY-BRIEF-001, R2-H):** `write_incident` writes the per-incident history
   `out/{incident_id}.json`, copies it to the fixed `out/incident_replay_brief.json`, and renders
   `out/pika_prompt.md`.
4. **Prompt contract (REPLAY-BRIEF-002):** `render_pika_prompt` emits the synthetic-data-only / no-PHI
   safety rules, autonomous-coordination emphasis, requested outputs, and the return contract
   (asset URL/ID, `task_id`, tool, summary). `scripts/build_pika_prompt.py` re-renders from a brief.
5. **No empty artifacts (REPLAY-BRIEF-003):** `export_incident` returns None and writes nothing when
   there are no milestone lines; `orchestrator._emit_replay` skips when no store or no lines.

**Orchestrator integration:** `_replay = ReplayRecorder()` (per-run state); `_emit_replay(ctx, event,
lines)` is best-effort (export failure is logged, never crashes the command). Oxygen lines live on the
`flow_id`-keyed `OxygenFlow.lines` so overlapping/autonomous flows don't share a buffer.

## EARS Coverage

| Category | Spec IDs | Implemented | Deferred | Gaps |
|----------|----------|-------------|----------|------|
| Log | REPLAY-LOG-001, REPLAY-LOG-002 | 2 | 0 | 0 |
| Brief | REPLAY-BRIEF-001..004 | 4 | 0 | 0 |

**Summary:** 6 of 6 active REPLAY specs implemented + tested. The Pika MCP media-generation step is
out of EARS scope (external Claude-Code-CLI post-processing — Phase P); this arrow stops at the files.

## Key Findings

1. **Pure derivation + thin recorder** — `build_brief`/`render_pika_prompt`/`export_incident` are pure
   over a `StorageInterface` snapshot and a target dir, so the whole layer is unit-tested with hand-built
   line lists + `tmp_path`; no live Bureau. The recorder owns only `seq` + incident counters.
2. **`seq` is global+monotonic; `t` is per-incident** — the `er:events` line carries the absolute `seq`
   (REPLAY-LOG-002 ordering), while the brief's `timeline[].t` is derived from the **relative** seq
   within the incident (`(seq - base)×5`), keeping the example `00:00, 00:05, …` sane across multiple
   incidents in one run. Resolves the LLD §9 / Gap-9 "seq*5 < 60" tension.
3. **Milestone reuse for intake** — intake doesn't re-derive milestones; the Orchestrator publishes
   `run_intake`'s existing returned `milestones` list verbatim (`**m["detail"]`), keeping `run_intake`
   pure and the publish at the Orchestrator boundary (matches LLD "Orchestrator publish()es").
4. **Boundary held** — no Pika/fal.ai client in `er_twin/`; the runtime only writes `out/*`. `.gitignore`
   switched to `out/*` + `!out/.gitkeep` so the dir is tracked but artifacts stay ignored.

## Work Required

### Must Fix
_None — all 6 REPLAY specs implemented + tested; intake chain verified on disk._

### Should Fix
_None._

### Nice to Have
1. Live in-Bureau emission of oxygen/summary briefs needs the one-time Agentverse inspector connect to
   exercise via chat; the unit tests + the on-disk intake run are the automatable proof. A live-Bureau
   spike (like `oxygen_async_flow_spike.py`) could assert the oxygen brief end-to-end if desired.
2. Phase P consumes these files: `scripts/run_pika_identity_check.ps1` + `scripts/run_pika_replay.ps1`
   (Claude Code CLI → Pika MCP, explicit `--allowedTools`, `permission_denials` check).
