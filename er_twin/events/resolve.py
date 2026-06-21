"""Resolve active events — chat or dashboard archives to event log."""

from __future__ import annotations

import re

from er_twin import active_events
from er_twin.events.base import DispatchContext, EventHandler
from er_twin.events.discharge_flow import release_patient_resources


class ResolveHandler(EventHandler):
    key = "resolve"
    keywords = ("resolve event", "resolve", "close event")
    mock_reply = "Specify an event id to resolve (e.g. resolve evt-0001)."
    incident_type = "event_resolved"
    visual_style = "clean hospital operations closure"

    async def dispatch(self, dctx: DispatchContext) -> bool:
        if dctx.store is None:
            await dctx.send_chat(dctx.ctx, dctx.cmd.sender, self.mock_reply)
            return True
        event_id = self._parse_event_id(dctx.cmd.text)
        if not event_id:
            events = active_events.list_active_events(dctx.store)
            if not events:
                await dctx.send_chat(dctx.ctx, dctx.cmd.sender, "No current events to resolve.")
                return True
            listing = "\n".join(f"  • {e['id']}: {e['summary'][:60]}" for e in events)
            await dctx.send_chat(
                dctx.ctx, dctx.cmd.sender,
                f"Current events:\n{listing}\nReply \"resolve evt-0001\" to close one.",
                end_session=False,
            )
            return True
        return await self._resolve(dctx, event_id)

    def _parse_event_id(self, text: str) -> str | None:
        m = re.search(r"\b(evt-\d{4})\b", text, re.IGNORECASE)
        return m.group(1).lower() if m else None

    async def _resolve(self, dctx: DispatchContext, event_id: str) -> bool:
        store = dctx.store
        assert store is not None
        rec = active_events.resolve_active_event(store, event_id, dctx.replay)
        if rec is None:
            await dctx.send_chat(dctx.ctx, dctx.cmd.sender, f"Event {event_id} not found or already resolved.")
            return True
        if rec.get("type") == "discharge" and rec.get("patient_id"):
            release_patient_resources(store, rec["patient_id"])
        msg = f"Resolved {event_id} ({rec.get('type', 'event')}) — moved to event log."
        dctx.record_memory(dctx.ctx, msg)
        await dctx.send_chat(dctx.ctx, dctx.cmd.sender, msg)
        return True


def resolve_event_from_dashboard(store, event_id: str, replay_recorder) -> dict | None:
    """Dashboard API entry point for resolving an active event."""
    rec = active_events.resolve_active_event(store, event_id, replay_recorder)
    if rec is None:
        return None
    if rec.get("type") == "discharge" and rec.get("patient_id"):
        release_patient_resources(store, rec["patient_id"])
    return rec
