#!/usr/bin/env python
"""Redis layer smoke test — run before the demo to verify the full stack.

Checks:
  1. Hash round-trip via RedisStore (set → get → compare)
  2. Index set via list_ids()
  3. Stream event via XADD / XLEN
  4. Iris Agent Memory health (skipped if AGENT_MEMORY_* vars are absent)

Usage:
    uv run python scripts/redis_smoke.py

Exit code 0 = all checks passed.  Non-zero = something is broken.
"""

import sys

sys.path.insert(0, ".")  # ensure er_twin package is importable from the repo root

from er_twin.config import settings

PASS = "  OK "
FAIL = " FAIL"
SKIP = " SKIP"


def check(label: str, ok: bool | None, detail: str = "") -> bool:
    """Print a result line and return whether the check passed."""
    if ok is None:
        print(f"[{SKIP}] {label}{' — ' + detail if detail else ''}")
        return True  # skip is not a failure
    status = PASS if ok else FAIL
    print(f"[{status}] {label}{' — ' + detail if detail else ''}")
    return ok


def main() -> int:
    failures = 0

    # ------------------------------------------------------------------
    # 1. RedisStore — hash round-trip
    # ------------------------------------------------------------------
    if not settings.redis_url:
        check("RedisStore: hash round-trip", None, "REDIS_URL not set")
        check("RedisStore: index set", None, "REDIS_URL not set")
        check("RedisStore: Stream event", None, "REDIS_URL not set")
    else:
        from er_twin.storage import RedisStore

        store = RedisStore(settings.redis_url)
        smoke_key = "er:patient:__smoke__"

        try:
            # clean up first
            store._client.delete(smoke_key)
            store._client.srem("er:index:patient", "__smoke__")

            # hash write + read
            store.set(smoke_key, {"name": "Smoke", "acuity": 1, "available": True, "care_team": ["n1"]})
            record = store.get(smoke_key)
            ok = record.get("name") == "Smoke" and record.get("acuity") == 1
            failures += 0 if check("RedisStore: hash round-trip", ok) else 1

            # index set
            ids = store.list_ids("patient")
            failures += 0 if check("RedisStore: index set", "__smoke__" in ids) else 1

            # Stream
            store.publish("er:events", '{"event": "smoke_test"}')
            stream_len = store._client.xlen("er:events")
            failures += 0 if check("RedisStore: Stream event", stream_len >= 1, f"stream len={stream_len}") else 1

        finally:
            store._client.delete(smoke_key)
            store._client.srem("er:index:patient", "__smoke__")

    # ------------------------------------------------------------------
    # 2. Iris Agent Memory health
    # ------------------------------------------------------------------
    iris_vars = (settings.agent_memory_base_url, settings.agent_memory_store_id, settings.agent_memory_api_key)
    if not all(iris_vars):
        check("Iris Agent Memory: health", None, "AGENT_MEMORY_* vars not set")
    else:
        try:
            from er_twin.memory import IrisMemory

            mem = IrisMemory(
                base_url=settings.agent_memory_base_url,
                store_id=settings.agent_memory_store_id,
                api_key=settings.agent_memory_api_key,
            )
            health = mem._client.health()
            ok = health is not None
            failures += 0 if check("Iris Agent Memory: health", ok, str(health)) else 1
            mem.close()
        except Exception as exc:
            failures += 0 if check("Iris Agent Memory: health", False, str(exc)) else 1

    # ------------------------------------------------------------------
    # summary
    # ------------------------------------------------------------------
    print()
    if failures == 0:
        print("All checks passed. Redis layer is ready for the demo.")
    else:
        print(f"{failures} check(s) FAILED. Fix the issues above before the demo.")

    return failures


if __name__ == "__main__":
    sys.exit(main())
