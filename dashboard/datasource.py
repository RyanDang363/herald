"""Dashboard data source — assemble read-only snapshots through StorageInterface.

@spec DASH-API-001, DASH-API-003, DASH-SYS-001, DASH-SYS-002, DASH-SYS-004

The same `snapshot()` works for fixture mode and Redis mode; only which `StorageInterface`
`get_store()` returns differs (the LLD §2 fixture↔Redis seam).
"""

import json
import time
from collections import deque
from pathlib import Path

from er_twin.config import settings
from er_twin.storage import InMemoryStore, StorageInterface

# Entity type -> snapshot key (plural). Equipment stays "equipment".
ENTITIES: dict[str, str] = {
    "patient": "patients",
    "bed": "beds",
    "nurse": "nurses",
    "doctor": "doctors",
    "equipment": "equipment",
}

# Dummy threshold for the read-only baseline. MUST be reconciled with the value the
# EquipmentAgent uses for OXY-FLOW-001 before the live demo (see dashboard.lld.md §2).
LOW_OXYGEN_THRESHOLD = 50

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "er_state.json"
_fixture_store: InMemoryStore | None = None


def build_fixture_store() -> InMemoryStore:
    """Load the JSON fixture into an InMemoryStore keyed `er:{entity}:{id}`."""
    data = json.loads(_FIXTURE_PATH.read_text())
    store = InMemoryStore()
    for entity, plural in ENTITIES.items():
        for record in data.get(plural, []):
            store.set(f"er:{entity}:{record['id']}", record)
    return store


def get_store() -> StorageInterface:
    """Return the configured store. Fixture is cached; Redis is constructed per call."""
    global _fixture_store
    if settings.dashboard_source == "redis":
        # Imported lazily: RedisStore is Dev 2's Phase 6 work and may not exist yet.
        from er_twin.storage import RedisStore  # type: ignore[attr-defined]

        return RedisStore(settings.redis_url)
    if _fixture_store is None:
        _fixture_store = build_fixture_store()
    return _fixture_store


def snapshot(store: StorageInterface) -> dict:
    """Assemble the full ER snapshot via the storage interface only. @spec DASH-SYS-004"""
    out: dict = {}
    for entity, plural in ENTITIES.items():
        ids = store.list_ids(entity)
        out[plural] = [store.get(f"er:{entity}:{eid}") for eid in ids]
    return out


def derive_summary(snap: dict) -> dict:
    """Display-only KPIs derived from a snapshot — no state mutation. @spec DASH-API-003"""
    patients = snap.get("patients", [])
    beds = snap.get("beds", [])
    nurses = snap.get("nurses", [])
    doctors = snap.get("doctors", [])
    equipment = snap.get("equipment", [])
    return {
        "active_patients": sum(1 for p in patients if p.get("status") != "discharged"),
        "occupied_beds": sum(1 for b in beds if b.get("status") == "occupied"),
        "free_nurses": sum(1 for n in nurses if n.get("available")),
        "free_doctors": sum(1 for d in doctors if d.get("available")),
        "active_alerts": sum(1 for e in equipment if _is_low_oxygen(e)),
    }


def _is_low_oxygen(equip: dict) -> bool:
    level = equip.get("supply_level")
    return equip.get("type") == "oxygen" and level is not None and level < LOW_OXYGEN_THRESHOLD


class EventBuffer:
    """Ring buffer of the most recent `er:events` lines. @spec DASH-API-004, DASH-SYS-003"""

    def __init__(self, maxlen: int = 50) -> None:
        self._events: deque[dict] = deque(maxlen=maxlen)

    def add(self, event: dict) -> None:
        self._events.append(event)

    def recent(self) -> list[dict]:
        return list(self._events)


# Fixture events so the log panel is demonstrable without a running Bureau.
_FIXTURE_EVENTS = [
    {
        "ts": "2026-06-20T12:00:01",
        "event": "intake",
        "detail": "Jordan Lee admitted (chest pain), ESI-2 → bed1",
    },
    {
        "ts": "2026-06-20T12:00:02",
        "event": "staff",
        "detail": "nurse1 + doc1 (cardiology) assigned to p1",
    },
    {
        "ts": "2026-06-20T12:01:10",
        "event": "triage",
        "detail": "Sam Rivera triaged ESI-3 (ankle injury)",
    },
    {"ts": "2026-06-20T12:02:30", "event": "alert", "detail": "o2_1 supply low (45%) in storage"},
]


def build_event_buffer(maxlen: int = 50) -> EventBuffer:
    """Event buffer; seeded with fixture events when not in Redis mode."""
    buf = EventBuffer(maxlen=maxlen)
    if settings.dashboard_source not in ("redis", "sim"):
        for ev in _FIXTURE_EVENTS:
            buf.add(ev)
    return buf


_fixture_buffer: EventBuffer | None = None


def live_snapshot() -> dict:
    """Snapshot for the current source — fixture, redis, or the scripted sim. @spec DASH-SIM-001"""
    if settings.dashboard_source == "sim":
        from .sim import controller

        state, _ = controller.state_and_events(time.monotonic())
        return state
    return snapshot(get_store())


def current_events() -> list[dict]:
    """Event lines for the current source. @spec DASH-SIM-002, DASH-API-004"""
    global _fixture_buffer
    if settings.dashboard_source == "sim":
        from .sim import controller

        _, events = controller.state_and_events(time.monotonic())
        return events
    if _fixture_buffer is None:
        _fixture_buffer = build_event_buffer()
    return _fixture_buffer.recent()
