"""Current (active) ER events — lifecycle before admin resolve.

Active events live at `er:active_event:{id}` with index `er:index:active_event`.
Resolving archives a summary line to `er:events` and removes the active record.

@spec RESOLVE-FLOW-001 @spec RESOLVE-STATE-001
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from er_twin.storage import StorageInterface

if TYPE_CHECKING:
    from er_twin.replay import ReplayRecorder

COUNTER_KEY = "er:counter:active_event"


def _event_key(event_id: str) -> str:
    return f"er:active_event:{event_id}"


def _next_id(store: StorageInterface) -> str:
    n = int(store.get(COUNTER_KEY).get("n", 0)) + 1
    store.set(COUNTER_KEY, {"n": n})
    return f"evt-{n:04d}"


def create_active_event(
    store: StorageInterface,
    event_type: str,
    summary: str,
    patient_id: str = "",
    incident_id: str = "",
    flow_id: str = "",
    status: str = "active",
    extra_data: dict | None = None,
) -> str:
    """Register a new current event; returns the event id."""
    event_id = _next_id(store)
    record: dict = {
        "id": event_id,
        "type": event_type,
        "patient_id": patient_id,
        "summary": summary,
        "status": status,
        "ts": time.time(),
        "incident_id": incident_id,
        "flow_id": flow_id,
    }
    if extra_data:
        record.update(extra_data)
    store.set(_event_key(event_id), record)
    return event_id


def list_active_events(store: StorageInterface) -> list[dict]:
    """All non-resolved current events (active + pending_approval), oldest first."""
    live_statuses = {"active", "pending_approval"}
    events = [
        store.get(_event_key(eid)) for eid in store.list_ids("active_event")
        if store.get(_event_key(eid)).get("status") in live_statuses
    ]
    return sorted(events, key=lambda e: e.get("ts", 0))


def get_active_event(store: StorageInterface, event_id: str) -> dict | None:
    rec = store.get(_event_key(event_id))
    return rec if rec.get("id") else None


def confirm_pending_proposal(
    store: StorageInterface,
    event_id: str,
    confirmation_summary: str,
    new_type: str | None = None,
) -> bool:
    """Promote a pending_approval event to active after assignments are confirmed. Returns True if promoted."""
    rec = get_active_event(store, event_id)
    if not rec or rec.get("status") != "pending_approval":
        return False
    updates: dict = {"status": "active", "summary": confirmation_summary}
    if new_type:
        updates["type"] = new_type
    store.update(_event_key(event_id), updates)
    return True


def resolve_active_event(
    store: StorageInterface,
    event_id: str,
    recorder: ReplayRecorder | None = None,
) -> dict | None:
    """Archive an active event to the log and remove it. Returns the event record or None."""
    rec = get_active_event(store, event_id)
    if not rec or rec.get("status") != "active":
        return None
    if recorder is not None:
        recorder.log(
            store,
            rec.get("type", "event"),
            "admin",
            "event_resolved",
            event_id,
            patient_id=rec.get("patient_id", ""),
            summary=rec.get("summary", ""),
        )
    else:
        store.publish(
            "er:events",
            json.dumps(
                {
                    "event": rec.get("type", "event"),
                    "actor": "admin",
                    "action": "event_resolved",
                    "target": event_id,
                    "detail": {"summary": rec.get("summary", ""), "patient_id": rec.get("patient_id", "")},
                }
            ),
        )
    store.update(_event_key(event_id), {"status": "resolved"})
    return rec
