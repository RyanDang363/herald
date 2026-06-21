"""Idempotent seed for the live backend — decouples demo-state seeding from app boot.

Why this exists: `er_twin.main` seeds on every boot, but against a persistent `RedisStore` a partial
or missing seed silently degrades every intake to `no_bed_available`. Run this before a live
(`USE_MOCK=false`) demo to guarantee — and verify — that the ER inventory exists in Redis,
independently of starting the Bureau.

Usage:
    USE_MOCK=false uv run python scripts/seed_redis.py

Exits 0 when beds + nurses are present after seeding; non-zero (with a clear message) otherwise, so
an operator pre-flight / CI step fails loudly instead of discovering it mid-demo.
"""

from __future__ import annotations

import pathlib
import sys

# Allow running as a loose script (`python scripts/seed_redis.py`) — the project isn't an editable
# install, so put the repo root on sys.path before importing the package.
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from er_twin.config import settings  # noqa: E402
from er_twin.main import ensure_seeded  # noqa: E402
from er_twin.storage import make_store  # noqa: E402


def main() -> int:
    store = make_store()
    counts = ensure_seeded(store)
    print(f"backend   = {type(store).__name__} (USE_MOCK={settings.use_mock})")
    print(
        f"inventory = {counts['patient']} patients, {counts['bed']} beds, {counts['nurse']} nurses, "
        f"{counts['doctor']} doctors, {counts['equipment']} equipment"
    )
    ok = counts["bed"] > 0 and counts["nurse"] > 0
    if ok:
        print("OK — core inventory present; intakes can be admitted to a bed.")
        return 0
    print(
        "FAILED — beds/nurses missing after seed. Check REDIS_URL connectivity and that USE_MOCK is "
        "false so a RedisStore (not a throwaway InMemoryStore) is being seeded."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
