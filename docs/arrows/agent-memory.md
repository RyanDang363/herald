# Arrow: agent-memory

**Status**: PARTIAL  
**Audited**: 2026-06-20  
**HLD SHA at audit**: `8513c74`

## References

| Artifact | Path |
|---|---|
| HLD | [`README.md`](../../README.md) — §Iris / Agent Memory |
| LLD | [`docs/llds/er-twin-core.lld.md`](../llds/er-twin-core.lld.md) — §Agent Memory Contract |
| EARS | [`docs/specs/er-events-specs.md`](../specs/er-events-specs.md) — `MEM-FLOW-001`, `MEM-FLOW-002`, `MEM-ERR-001`, `MEM-IDEM-001` |
| Code | `er_twin/memory.py` |
| Tests | `tests/test_memory.py` |
| Config | `er_twin/config.py` — `agent_memory_*` settings |

## Domain

Semantic long-term memory for the OrchestratorAgent. Uses Redis Iris (Agent Memory Server on Redis Cloud 2.5 GB instance). Provides a `MemoryInterface` abstraction:

- **`IrisMemory`** — wraps `redis-agent-memory` SDK; activated when all three `AGENT_MEMORY_*` env vars are set and `USE_MOCK` is false.
- **`NoopMemory`** — silent no-op; activated in mock/offline mode.

`make_memory()` factory selects backend from env.

## Spec Coverage

| Spec ID | Status | Notes |
|---|---|---|
| `MEM-FLOW-001` | `[x]` | `IrisMemory.record_event()` calls SDK `add_session_memory`; `storage.publish()` writes to `er:events` stream |
| `MEM-FLOW-002` | `[x]` | `IrisMemory.recall()` calls SDK `search_memory` with natural-language query |
| `MEM-ERR-001` | `[x]` | `make_memory()` returns `NoopMemory` when vars absent or `USE_MOCK=true` |
| `MEM-IDEM-001` | `[D]` | Append-only by design; Iris SDK handles deduplication downstream. Our code never deduplicates before appending — correct per spec. |

**4 of 4 active specs done (1 deferred to Iris).**

## Implementation Findings

`IrisMemory` and `NoopMemory` are fully implemented and tested. Integration tests run against live Iris when `AGENT_MEMORY_*` env vars are set; they skip gracefully otherwise.

The module is ready for Dev 1 to inject into the Orchestrator. See `docs/TEAM.md §Redis layer handoff` for wiring instructions.

## Remaining Work

**Dev 1 action required** — the module is complete; the Orchestrator agent (in `core-agents`) must actually call it:

- After every ER event outcome, call `memory.record_event(session_id, "Patient {name} admitted to bed {bed_id}")`.
- Before every status-summary LLM call, call `memory.recall(session_id, query)` and inject the returned string into the prompt context.

These call sites are tracked under `core-agents` (MEM-FLOW-001 and MEM-FLOW-002 agent integration).
