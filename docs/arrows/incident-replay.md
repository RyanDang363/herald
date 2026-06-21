# Arrow: incident-replay

The own-surface boundary to Pika MCP (LLD §9 + §9.1). The Fetch runtime never calls Pika; everything
crosses a **file boundary in `out/`**. Two layers: **(1)** Phase R's narrative brief — the Orchestrator
publishes one structured JSON line per **milestone** to `er:events` and `replay.py` derives
`out/{incident_id}.json` + `out/incident_replay_brief.json` + `out/pika_prompt.md`; **(2)** the
data-driven replay (LLD §9.1) — each milestone also captures a full-state snapshot into
`out/replay/{incident}.json`, a `/replay` page reuses the dashboard floor map for ts-paced playback,
keyframe PNGs feed Pika `generate_keyframes_video`, and a gated `/library` lists the session's clips.
The Claude Code CLI → Pika MCP step (Phase P / `run_pika_keyframes.ps1`) reads those files.

## Status

**OK** — 2026-06-21. Two layers, both green. **(1) Narrative brief** (Phase R): 6/6
REPLAY-LOG/BRIEF specs `[x]`. **(2) Data-driven replay** (LLD §9.1, R+): full-state snapshot timeline →
`out/replay/{incident}.json` (per-milestone `ts`; intake captured *live* via the `run_intake`
`on_milestone` hook so intermediate states are real), a `/replay/{incident}` playback page that reuses
the dashboard `floor.js` and tweens tokens by real `ts` deltas, `scripts/capture_replay_frames.py`
(Playwright — **run-verified**, PNGs written), `scripts/run_pika_keyframes.ps1` (single start→end
`generate_keyframes_video` clip + `video_url` writeback — built + parse-checked), and a gated `/library`
page. 14 new `REPLAY-SNAP/FRAME/KEY/PIKA/LIB` specs `[x]`. **180 tests green + `ruff` clean**; replay +
library pages screenshotted.

`REPLAY-LOG-002` and the `er:events` line shape are **unchanged** (guard test
`test_log_line_shape_unchanged_by_snapshot_wiring`); the layer is **independent of `DASH-SYS-002`**
(file boundary, not Redis keys). The only step not exercised here is the **live Pika render** (operator
pre-flight, spends credits) — the same external boundary as the brief's Phase P.

_Earlier (Phase R, 2026-06-20): 8 replay tests + 61 prior = 69/69 pass; the full intake chain verified
on disk. HLD (README) SHA `8e87478` unchanged._

## References

| Type | Location |
|------|----------|
| HLD — incident replay / demo media | [README.md](../../README.md) (data-driven replay paragraph) |
| LLD — §9 (event-log line, brief schema, prompt contract) + §9.1 (snapshot timeline, replay page, keyframes, library) | [docs/llds/er-twin-core.lld.md](../llds/er-twin-core.lld.md) |
| Decisions — Gap 9 (seq/incident counters), R2-G (milestone granularity), R2-H (brief derivation + multi-event output) | [Round 1](../decisions/2026-06-20-event-flow-decisions.md) · [Round 2 §G/§H](../decisions/2026-06-20-round-2-event-mechanics.md) |
| EARS — 20 active REPLAY-* specs (6 LOG/BRIEF + 14 SNAP/FRAME/KEY/PIKA/LIB) | [docs/specs/er-events-specs.md](../specs/er-events-specs.md) |
| Tests | [tests/test_replay.py](../../tests/test_replay.py) (snapshot/timeline/keyframe/clip-duration), [tests/test_dashboard.py](../../tests/test_dashboard.py) (replay + library endpoints) |
| Code (brief) | [replay.py](../../er_twin/replay.py) (`ReplayRecorder`, `build_brief`, `render_pika_prompt`, `write_incident`, `export_incident`), [orchestrator.py](../../er_twin/agents/orchestrator.py) (`_replay`, `_emit_replay`), [scripts/build_pika_prompt.py](../../scripts/build_pika_prompt.py) |
| Code (data-driven, LLD §9.1) | [replay.py](../../er_twin/replay.py) (`ReplayRecorder.snapshot`/`timeline`/`snapshots_for`, `select_keyframes`, `requested_clip_duration`, `build_incident_timeline`, `export_incident_timeline`), [orchestrator.py](../../er_twin/agents/orchestrator.py) (`_log_milestone`, `run_intake(on_milestone=…)`, `_replay_note`), [dashboard/server.py](../../dashboard/server.py) (`/replay`, `/api/replay`, `/library`, `/api/library`), [dashboard/static/floor.js](../../dashboard/static/floor.js), [replay.{html,js}](../../dashboard/static/replay.js), [library.{html,js}](../../dashboard/static/library.js), [scripts/capture_replay_frames.py](../../scripts/capture_replay_frames.py), [scripts/run_pika_keyframes.ps1](../../scripts/run_pika_keyframes.ps1) |

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
| Snapshot | REPLAY-SNAP-001..003 | 3 | 0 | 0 |
| Frame | REPLAY-FRAME-001, REPLAY-FRAME-002 | 2 | 0 | 0 |
| Keyframe | REPLAY-KEY-001, REPLAY-KEY-002 | 2 | 0 | 0 |
| Pika | REPLAY-PIKA-001, REPLAY-PIKA-002 | 2 | 0 | 0 |
| Library | REPLAY-LIB-001..005 | 5 | 0 | 0 |

**Summary:** 20 of 20 active REPLAY specs implemented + tested. The two Pika invocation specs
(`REPLAY-PIKA-001` clip generation, `REPLAY-LIB-003` `video_url` writeback) are **script-driven** —
their `@spec` annotations live in `scripts/run_pika_keyframes.ps1`; the live render is external
post-processing (operator pre-flight, spends credits), the same boundary as the brief's Phase P. Every
in-runtime / pure-logic spec is covered by `pytest` (`test_replay.py` + `test_dashboard.py`), and the
replay + library pages and captured frames were screenshotted.

## Key Findings

1. **Pure derivation + thin recorder** — `build_brief`/`render_pika_prompt`/`export_incident` are pure
   over a `StorageInterface` snapshot and a target dir, so the whole layer is unit-tested with hand-built
   line lists + `tmp_path`; no live Bureau. The recorder owns only `seq` + incident counters.
2. **`seq` is global+monotonic; `t` is per-incident** — the `er:events` line carries the absolute `seq`
   (REPLAY-LOG-002 ordering), while the brief's `timeline[].t` is derived from the **relative** seq
   within the incident (`(seq - base)×5`), keeping the example `00:00, 00:05, …` sane across multiple
   incidents in one run. Resolves the LLD §9 / Gap-9 "seq*5 < 60" tension.
3. **Live milestone capture for intake** — the Orchestrator drives intake through a
   `run_intake(on_milestone=…)` hook, so each `er:events` line **and** its full-state snapshot are taken
   at the real moment of the milestone. This was a deliberate fix: capturing after `run_intake` returned
   gave every snapshot the same final state (keyframes collapsed to one), so synchronous intake showed no
   motion. `on_milestone` defaults to `None`, keeping `run_intake` pure for the existing callers/tests.
4. **Boundary held** — no Pika/fal.ai client in `er_twin/`; the runtime only writes `out/*` (now incl.
   `out/replay/` + `out/frames/`). `.gitignore` is `out/*` + `!out/.gitkeep`, so artifacts stay ignored.
5. **Data-driven replay shares the live floor + holds REPLAY-LOG-002** — floor geometry/placement was
   extracted from `app.js` into `floor.js` (`window.Floor.placeEntities`) and reused by both the
   dashboard and `/replay`, so the reconstruction is the same map (no behavior change to the live
   dashboard — verified by screenshot). `ts` lives only on the snapshot records; the `er:events` line
   shape is unchanged, asserted by `test_log_line_shape_unchanged_by_snapshot_wiring`. The Pika keyframe
   cap was **verified = 2** against the MCP schema (`first_frame`+`last_frame`, `duration ∈ {5,10}`), so
   selection degrades to start→end and the clip is one `generate_keyframes_video` call.

## Work Required

### Must Fix
_None — all 20 active REPLAY specs implemented + tested (intake chain verified on disk; replay/library
pages + captured frames screenshotted)._

### Should Fix
_None._

### Nice to Have
1. **Run the live Pika render once** (`run_pika_keyframes.ps1`) to exercise `REPLAY-PIKA-001` +
   `REPLAY-LIB-003` end-to-end and confirm a real `video_url` embeds in `/library`. Spends credits, so
   it's an operator pre-flight step (the same external boundary as Phase P) — pre-generate before judging.
2. Live in-Bureau emission of oxygen/summary incidents needs the one-time Agentverse inspector connect to
   exercise via chat; the unit tests + the on-disk intake run are the automatable proof. A live-Bureau
   spike (like `oxygen_async_flow_spike.py`) could assert the oxygen timeline end-to-end if desired.
3. Frame capture depends on a one-time `uv run playwright install chromium`; if Chromium is unavailable
   on the day, swap the rasterizer for `resvg`/`cairosvg` on the same SVG (selection + Pika step unchanged).
