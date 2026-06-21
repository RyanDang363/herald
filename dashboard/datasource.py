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


def _event_row(entry_id: str, line: dict) -> dict:
    """Map one `er:events` stream line ({seq,event,actor,action,target,detail}) to a display row.

    The Orchestrator's `ReplayRecorder` publishes those structured lines; the dashboard renders the
    `{ts, event, detail}` shape its feed expects (the same shape as the fixture events). `ts` is the
    Redis stream entry id's millisecond component (the broker's wall-clock, not er_twin's).
    @spec DASH-SYS-003
    """
    detail = line.get("detail") or {}
    detail_str = ", ".join(f"{k}={v}" for k, v in detail.items() if v not in (None, ""))
    text = line.get("action", "event")
    target = line.get("target")
    if target:
        text += f" → {target}"
    if detail_str:
        text += f" ({detail_str})"
    ts = entry_id.split("-")[0] if isinstance(entry_id, str) else str(entry_id)
    return {"ts": ts, "event": line.get("event", "event"), "detail": text}


def _redis_events(maxlen: int = 50) -> list[dict]:
    """Read the most recent `er:events` stream lines from Redis (newest-capped, returned oldest-first).

    Polled by `/api/events`; uses XREVRANGE on the same Stream `RedisStore.publish` XADDs to, so the
    dashboard replays history a live subscriber would miss. Any connection/parse error degrades to an
    empty feed rather than erroring the endpoint (read-only, best-effort). @spec DASH-SYS-002, DASH-SYS-003
    """
    client = getattr(get_store(), "_client", None)
    if client is None:
        return []
    try:
        entries = client.xrevrange("er:events", count=maxlen)
    except Exception:  # noqa: BLE001 — a dead/unreachable Redis must not 500 the dashboard.
        return []
    rows: list[dict] = []
    for entry_id, fields in entries:
        try:
            line = json.loads(fields.get("msg", ""))
        except (json.JSONDecodeError, TypeError):
            continue
        rows.append(_event_row(entry_id, line))
    rows.reverse()  # XREVRANGE is newest-first; the feed reads oldest-first.
    return rows


def list_active_events_store(store: StorageInterface) -> list[dict]:
    """Read current (unresolved) events from `er:active_event:*`. @spec RESOLVE-FLOW-001"""
    from er_twin.active_events import list_active_events

    return list_active_events(store)


def active_events_list() -> list[dict]:
    """Active events for the configured dashboard source."""
    if settings.dashboard_source == "sim":
        return []
    if settings.dashboard_source == "redis":
        try:
            return list_active_events_store(get_store())
        except Exception:  # noqa: BLE001
            return []
    return []


def current_events() -> list[dict]:
    """Event lines for the current source. @spec DASH-SIM-002, DASH-API-004, DASH-SYS-003"""
    global _fixture_buffer
    if settings.dashboard_source == "sim":
        from .sim import controller

        _, events = controller.state_and_events(time.monotonic())
        return events
    if settings.dashboard_source == "redis":
        return _redis_events()
    if _fixture_buffer is None:
        _fixture_buffer = build_event_buffer()
    return _fixture_buffer.recent()
