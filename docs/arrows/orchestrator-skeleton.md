# Arrow: orchestrator-skeleton

The single public, ASI:One-reachable surface (mailbox + Chat Protocol) and the first-slice in-process
loop: chat → intent resolve (USE_MOCK) → `PingRequest` to the private stub → reply relayed to chat.
This is the mandatory Fetch.ai judging path in miniature.

## Status

**OK** — 2026-06-20 (drift detected *and resolved* this session). All 9 active `ORCH-*` specs
implemented; suite green (53/53), `ruff` clean, boot verified. The `ORCH-SYS-003` ↔ `CommandGate`
divergence found during the Phase 4 audit has been fixed **code → spec**: `CommandGate` now represents
one command active across its full request→reply lifecycle (start on dispatch, finish only in the
terminal handler / watchdog), defers others via a queue, and a per-command watchdog releases the gate
if a reply is lost. `ORCH-LLM-001` (real ASI:One call) stays `[D]` deferred to Phase 5.

_Re-checked 2026-06-20 (event-flow decision cascade): HLD unchanged; the new `TriageResponse.specialty`
/ `SimulateOxygenDrop*` contracts and edited INTAKE/OXY/SUMM specs are all outside this arrow (Ping
loop untouched)._

## Drift Findings

_Resolved 2026-06-20 — kept for history._

1. **ORCH-SYS-003 ↔ `CommandGate` (spec ↔ code)** — detected and **resolved** 2026-06-20.
   * **Divergence (was):** `ORCH-SYS-003` requires full-lifecycle serialization ("defer … until the
     current one has produced a reply"), but the old `CommandGate.run()` wrapped only the synchronous
     `process()` body, which returned at the first `ctx.send`; the terminal reply was produced later in
     `on_pong` / `on_dispatch`, outside the lock — so a second command (or an autonomous
     `LowSupplyAlert`) could begin while a prior flow was mid-hop.
   * **Resolution (code → spec, as decided):** the new `CommandGate`
     ([orchestrator.py](../../er_twin/agents/orchestrator.py)) holds a single `active_flow_id` from
     dispatch until the terminal finalizer (`_complete_command` / `_finish_oxygen` / watchdog) frees
     it; commands arriving while busy are queued (`PendingChatCommand`) and run on completion; a
     `COMMAND_TIMEOUT_SECONDS` watchdog prevents a lost reply from wedging the gate. Threads the same
     `flow_id` as the `low-oxygen-alert` GAP-2 fix. Covered by
     `test_command_gate_defers_until_terminal_reply` + `test_command_gate_finish_ignores_stale_flow`
     ([tests/test_orchestrator_skeleton.py](../../tests/test_orchestrator_skeleton.py)).

## References

| Type | Location |
|------|----------|
| HLD — public-surface / one-process / USE_MOCK | [README.md](../../README.md) |
| LLD — §3 (Ping contract), §5 (first-slice control flow + async correlation), §6 (errors, serialization) | [docs/llds/er-twin-core.lld.md](../llds/er-twin-core.lld.md) |
| EARS — 9 active specs (`ORCH-*`) | [docs/specs/er-events-specs.md](../specs/er-events-specs.md) |
| Tests | [tests/test_orchestrator_skeleton.py](../../tests/test_orchestrator_skeleton.py) |
| Code | [er_twin/agents/orchestrator.py](../../er_twin/agents/orchestrator.py), [er_twin/agents/stub.py](../../er_twin/agents/stub.py), [er_twin/main.py](../../er_twin/main.py), [er_twin/addresses.py](../../er_twin/addresses.py) |

## Architecture

**Purpose:** Expose one public agent to ASI:One and prove the chat → internal-agent → chat loop runs
in-process inside a single Bureau, with deterministic addressing and the async correlation pattern.

**Key Components:**
1. `OrchestratorAgent` (`orchestrator.py`) — `mailbox=True`, `publish_agent_details=True`,
   `network="testnet"`; constructed `Protocol(spec=chat_protocol_spec)` included via `.include()`.
2. `resolve_intent` / `resolve_command` — pure USE_MOCK lookup (word-boundary matched) with
   LLM-error fallback; `_resolve_via_llm` is the deferred ASI:One seam.
3. `SessionSenders` + `_pending_ping_sessions` FIFO — async correlation across the chat↔stub session hop.
4. `CommandGate` — full-lifecycle serialization (one `active_flow_id` from dispatch until the terminal
   reply; queues deferred commands; `_watchdog` releases on timeout) — `ORCH-SYS-003`.
5. `StubAgent` (`stub.py`) — private Bureau member; `PingRequest → PingResponse`.
6. `main.build_bureau` — one Bureau holding both agents.

## EARS Coverage

| Category | Spec IDs | Implemented | Deferred | Gaps |
|----------|----------|-------------|----------|------|
| Chat surface | ORCH-CHAT-001/002 | 2 | 0 | 0 |
| System invariants | ORCH-SYS-001/002/003 | 3 | 0 | 0 |
| Intent / LLM | ORCH-LLM-001/002/003/004 | 3 | 1 (LLM-001) | 0 |
| Skeleton loop | ORCH-SKEL-001 | 1 | 0 | 0 |

**Summary:** 9 of 9 active specs implemented; 1 deferred (`ORCH-LLM-001`, real ASI:One call → Phase 5).

## Key Findings

1. **Behavioral specs fully traced** — `ORCH-CHAT-002` ([orchestrator.py:175](../../er_twin/agents/orchestrator.py#L175)),
   `ORCH-SKEL-001` ([orchestrator.py:190](../../er_twin/agents/orchestrator.py#L190),
   [:216](../../er_twin/agents/orchestrator.py#L216), [stub.py:21](../../er_twin/agents/stub.py#L21)),
   `ORCH-LLM-004` ([orchestrator.py:201](../../er_twin/agents/orchestrator.py#L201)),
   `ORCH-SYS-003` ([orchestrator.py:204](../../er_twin/agents/orchestrator.py#L204)) carry `@spec`
   annotations; `ORCH-LLM-002/003` are covered by tagged tests.
2. **Structural invariants verified by wiring, not inline annotation** — `ORCH-CHAT-001` (mailbox +
   chat protocol on startup), `ORCH-SYS-001` (one Bureau), and `ORCH-SYS-002` (seed-derived addresses)
   are realized by constructor args / `Bureau.add` / `addresses.py` rather than handler logic, so they
   have no line-level `@spec`. They are confirmed by the boot log (`Starting mailbox client`,
   `Manifest published successfully: AgentChatProtocol`, single server on :8000) and by a runtime check
   that `Agent(seed=seed_for(...)).address` equals the `addresses.py` constants. Not drift —
   constructor-level invariants aren't naturally line-annotatable.
3. **Ping bridges two sessions deliberately** — uAgents does not carry the chat session across the
   Orchestrator→stub→Orchestrator hop, so `SessionSenders` (keyed by chat session) plus a pending FIFO
   (now tagged by command `flow_id`) correlate the relay; `on_pong` frees the command gate. Safe
   because the lifecycle `CommandGate` keeps commands truly one-in-flight (see **Drift Findings** —
   resolved). Documented in the module docstring — do not "simplify" to synchronous req/resp.
4. **ASI:One deliberately not wired in P1** — `_resolve_via_llm` raises so `resolve_command` exercises
   the documented fallback (`ORCH-LLM-002`) whenever `USE_MOCK` is off; no `openai` dep added yet.

## Work Required

### Must Fix
_None — the `ORCH-SYS-003` ↔ `CommandGate` drift was resolved this session (see **Drift Findings**)._

### Should Fix
_None._

### Nice to Have
1. When the real ASI:One client lands in Phase 5, implement `_resolve_via_llm`, flip `ORCH-LLM-001`
   `[D]`→`[x]`, and re-audit (status stays OK).
