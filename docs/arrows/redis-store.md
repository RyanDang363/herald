# Arrow: redis-store

**Status**: OK  
**Audited**: 2026-06-20  
**HLD SHA at audit**: `8513c74`

## References

| Artifact | Path |
|---|---|
| HLD | [`README.md`](../../README.md) — §Redis |
| LLD | [`docs/llds/er-twin-core.lld.md`](../llds/er-twin-core.lld.md) — §Storage Contract |
| EARS | [`docs/specs/er-events-specs.md`](../specs/er-events-specs.md) — `INTAKE-FLOW-002`, `INTAKE-FLOW-004/006/008`, `INTAKE-STATE-001`, `SUMM-FLOW-001`, `MEM-FLOW-001 (event feed)` |
| Code | `er_twin/storage.py` |
| Tests | `tests/test_storage.py` |

## Domain

Persistence layer for all ER entity state. Provides a `StorageInterface` abstraction so agents are backend-agnostic. Two concrete backends:

- **`InMemoryStore`** — in-process dict; used in tests and when `REDIS_URL` is unset.
- **`RedisStore`** — `redis-py` client; hashes (`er:{entity}:{id}`), index sets (`er:index:{entity}`), and Redis Streams (`er:events`). JSON-encodes dict fields.

`make_store()` factory selects the backend from env.

## Spec Coverage

| Spec ID | Status | Notes |
|---|---|---|
| `INTAKE-FLOW-002` (storage side) | `[x]` | `storage.set()` persists patient hash |
| `INTAKE-STATE-001` (storage side) | `[x]` | `storage.set()` / `storage.update()` writes `status` field |
| `INTAKE-FLOW-004`, `-006`, `-008` (storage side) | `[x]` | `storage.update()` supports partial writes (triage, bed, staff) |
| `SUMM-FLOW-001` (storage side) | `[x]` | `storage.list_ids()` + `storage.get()` reads all entities |
| `MEM-FLOW-001` (event feed) | `[x]` | `storage.publish()` does `XADD er:events` |

> **Note**: These spec IDs are shared with the `core-agents` arrow. This arrow covers only the persistence half (write/read primitives); the agent message-handling half is tracked under `core-agents`.

## Implementation Findings

All 9 storage contract tests pass (parametrized across both backends). Redis integration tests activate when `REDIS_URL` is set in `.env` via `tests/conftest.py`.

Key behaviors verified:
- Hash round-trip with JSON type fidelity for nested dicts/lists.
- `er:index:{entity}` set maintained on every `set()` call.
- `er:events` stream written via `XADD` (not pub/sub); consumers use `XREAD`.
- `InMemoryStore` is a faithful drop-in for all tests.

## Remaining Work

None. This arrow is complete. Agent callers (Dev 1) are tracked under `core-agents`.
