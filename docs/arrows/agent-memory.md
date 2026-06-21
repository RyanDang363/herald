# Arrow: agent-memory

**Status**: OK  
**Audited**: 2026-06-21  
**HLD SHA at audit**: `8e87478` (integrated-tree README; reconciled from pre-integration `8513c74`)

## References

| Artifact | Path |
|---|---|
| HLD | [`README.md`](../../README.md) — §Iris / Agent Memory |
| LLD | [`docs/llds/er-twin-core.lld.md`](../llds/er-twin-core.lld.md) — §Agent Memory Contract |
| EARS | [`docs/specs/er-events-specs.md`](../specs/er-events-specs.md) — `MEM-FLOW-001`, `MEM-FLOW-002`, `MEM-ERR-001`, `MEM-IDEM-001` |
| Code | `er_twin/memory.py`; **integration:** `er_twin/agents/orchestrator.py` (`set_memory`, `_record_memory`, `_recall_memory`, `compose_summary`), `er_twin/main.py` (`make_memory()` injection) |
| Tests | `tests/test_memory.py`; **wiring:** `tests/test_integration_wiring.py` |
| Config | `er_twin/config.py` — `agent_memory_*` settings |

## Domain

Semantic long-term memory for the OrchestratorAgent. Uses Redis Iris (Agent Memory Server on Redis Cloud 2.5 GB instance). Provides a `MemoryInterface` abstraction:

- **`IrisMemory`** — wraps `redis-agent-memory` SDK; activated when all three `AGENT_MEMORY_*` env vars are set and `USE_MOCK` is false.
- **`NoopMemory`** — silent no-op; activated in mock/offline mode.

`make_memory()` factory selects backend from env.

## Spec Coverage

| Spec ID | Status | Notes |
|---|---|---|
| `MEM-FLOW-001` | `[x]` | `IrisMemory.record_event()` calls the SDK; **now invoked** from the Orchestrator's `_record_memory` at every terminal outcome — intake branch, `_finish_oxygen`, and the summary branch. Best-effort/non-fatal (wrapped like `_emit_replay`). |
| `MEM-FLOW-002` | `[x]` | `IrisMemory.recall()` queries long-term memory; **now invoked** via `_recall_memory` + `compose_summary` in the summary branch, folding recalled facts into the output. Empty under `NoopMemory` → template unchanged. |
| `MEM-ERR-001` | `[x]` | `make_memory()` returns `NoopMemory` when vars absent or `USE_MOCK=true`; the Orchestrator's seam swallows backend errors so a dead Iris never crashes a command. |
| `MEM-IDEM-001` | `[D]` | Append-only by design; Iris SDK handles deduplication downstream. Our code never deduplicates before appending — correct per spec. |

**4 of 4 active specs done (1 deferred to Iris) — fully wired into the Orchestrator.**

## Implementation Findings

`IrisMemory` and `NoopMemory` are implemented and tested. The Orchestrator integration landed 2026-06-21 (`evan/wire-memory-ehr-dashboard`): `main.py` injects `make_memory()` via `orch.set_memory()`; the Orchestrator records every event outcome and recalls before the summary, both non-fatal.

**Verified live** against Redis Cloud Iris: `record_event` → HTTP 201; `recall` returns a list (0 for a just-written event — Iris promotes session→long-term eventually). Unit-covered in `tests/test_integration_wiring.py` (record seam appends, swallows backend errors; `compose_summary` folds recall / is unchanged when empty). `test_memory.py` Iris integration tests pass live (creds bridged from `.env` by `conftest.py`).

## Remaining Work

None for the demo. **NEXT (with `ORCH-LLM-001`):** when a real ASI:One key is added, feed the recalled facts into the summary *LLM prompt* (the spec's original "prompt context" intent) rather than appending them to the template string.
