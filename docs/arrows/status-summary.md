# Arrow: status-summary

Event 3 — a **read-only, synchronous** ER status report. The chat command *"Show me what's happening
in the ER"* resolves to a summary intent; the Orchestrator reads the shared store directly and renders
a deterministic, state-derived template (decision R2-F). No async messaging, no state mutation, no
agent-to-agent hops — the whole event is one pure function plus a thin synchronous chat branch.

## Status

**OK** — 2026-06-20. Phase 5 complete and green: 8 summary tests + 53 prior = 61/61 pass,
`ruff check .` clean, 18 agents boot. All 4 active SUMM-* specs `[x]`. The real ASI:One LLM synthesis
path remains the deferred seam (shared with ORCH-LLM-001); USE_MOCK uses the store-derived template.

_Mapped + audited in one pass (Phase 5 landed this session). HLD (README) SHA `8e87478` unchanged
since the other arrows were audited — same upstream._

## References

| Type | Location |
|------|----------|
| HLD — Event 3, status summary | [README.md](../../README.md) |
| LLD — §7 (summary reads the store directly), §3 `StateQuery*` contract, §2 state shapes | [docs/llds/er-twin-core.lld.md](../llds/er-twin-core.lld.md) |
| Decisions — Gap 6 (R1 summary), R2-F (state-derived template + reconciliation) | [Round 1](../decisions/2026-06-20-event-flow-decisions.md) · [Round 2 §F](../decisions/2026-06-20-round-2-event-mechanics.md) |
| EARS — 4 active SUMM-* specs | [docs/specs/er-events-specs.md](../specs/er-events-specs.md) |
| Tests | [tests/test_event_summary.py](../../tests/test_event_summary.py) (8) |
| Code | [orchestrator.py](../../er_twin/agents/orchestrator.py) (`build_status_summary`, `_active_patients`, `_plural`, summary branch in `_dispatch_command`) |

## Architecture

**Purpose:** Answer a chat status query with a one-line, deterministic snapshot of the ER derived
entirely from current store state — never mutating it.

**Key Components / flow:**
1. **Intent (SUMM-FLOW-001):** `resolve_intent` maps the trigger phrases to `"summary"` (keywords
   already present since Phase 1).
2. **Pure render (SUMM-FLOW-002, R2-F):** `build_status_summary(store, active_o2_alert_beds)` reads
   patients/beds/nurses via `store.list_ids`/`store.get` and composes:
   - counts — active patients (status ∈ {waiting, in_triage, admitted, in_treatment}), occupied beds,
     free nurses, with count-aware pluralization matching the R2-F reconciliation strings;
   - an active-O2-alert line when `active_o2_alert_beds` is non-empty (bed named via `display`,
     pluralized for >1);
   - a "Most urgent: {name} (ESI-{acuity})" line for the lowest-acuity active patient ≤ 2 (tie-break
     by patient id ascending);
   - "No critical alerts." as the all-clear shown only when neither an alert nor an urgent line applies.
3. **Empty ER (SUMM-ERR-001):** if no active patients and no occupied beds, returns the calm
   "Nothing currently happening in the ER…" message instead.
4. **Synchronous chat branch:** the `intent == "summary"` branch in `_dispatch_command` computes the
   alert-bed list from the post-Phase-4 oxygen state (`oxygen_flows[fid].bed_id for fid in
   in_flight_o2_dispatches.values()`), calls `build_status_summary`, replies via `_send_chat`, and
   returns `True` — so the `CommandGate` frees immediately (no async tail).

**Read-only (SUMM-STATE-001):** `build_status_summary` only ever calls `store.get`/`store.list_ids`;
`test_summary_does_not_mutate_state` snapshots the store before/after and asserts equality.

## EARS Coverage

| Category | Spec IDs | Implemented | Deferred | Gaps |
|----------|----------|-------------|----------|------|
| Flow | SUMM-FLOW-001, SUMM-FLOW-002 | 2 | 0 | 0 |
| Errors | SUMM-ERR-001 | 1 | 0 | 0 |
| State | SUMM-STATE-001 | 1 | 0 | 0 |

**Summary:** 4 of 4 active SUMM specs implemented + tested. The ASI:One LLM synthesis alternative named
in SUMM-FLOW-002 is the same deferred seam as ORCH-LLM-001 (USE_MOCK template is the demo path).

## Key Findings

1. **Pure function + thin synchronous branch** — unlike intake (in-process coordinator) and oxygen
   (real async), the summary is a single pure render over the store; the chat branch is a wrapper that
   completes synchronously. Fully unit-tested against `InMemoryStore`; no spike needed.
2. **Reconciliation strings are the contract** — the two R2-F reconciliation outputs are asserted
   verbatim. Their behavior: "No critical alerts." is the all-clear shown *only* when there is neither
   an active O2 alert nor an urgent patient (the after-intake string omits it because a "Most urgent"
   line is present). This resolves the surface tension between the R2-F template sketch (which lists
   `{alert_summary}{urgent_summary}` with a standalone "No critical alerts.") and its own reconciliation
   examples — the reconciliation wins.
3. **O2-alert beds derived from flow state, injected** — the alert line needs the bed, but after the
   Phase-4 hardening `in_flight_o2_dispatches` maps `equipment_id → flow_id` and the bed lives on
   `oxygen_flows[flow_id].bed_id`. `build_status_summary` takes the bed list as a parameter (stays
   pure); the chat branch computes it. In normal gated demo operation the lifecycle `CommandGate`
   serializes a chat-triggered dispatch ahead of any summary, so the list is empty ("No critical
   alerts."); a non-empty list arises only from an autonomous alert mid-flight. Tested via injection.
4. **Dead mock path removed** — the Phase-1 `if intent in MOCK_REPLIES` fallthrough is gone now that
   intake/oxygen/summary each have a dedicated branch; `MOCK_REPLIES` survives only as the no-store
   fallback those branches reference (and the static summary string is illustrative-only per R2-F).

## Work Required

### Must Fix
_None — all 4 SUMM specs implemented + tested._

### Should Fix
_None._

### Nice to Have
1. Real ASI:One synthesis (SUMM-FLOW-002 LLM alternative) — implement alongside ORCH-LLM-001's
   `_resolve_via_llm`; the USE_MOCK template stays the deterministic demo path.
2. A `summary_generated` replay milestone (R2-G) is not yet published to `er:events` — wired in Phase R.
3. Manual chat run of *"Show me what's happening in the ER"* needs the one-time Agentverse inspector
   mailbox connect; the unit tests + boot are the automatable proof.
