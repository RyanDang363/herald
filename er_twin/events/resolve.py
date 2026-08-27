"""Resolve active events — chat or dashboard archives to event log."""

from __future__ import annotations

import re

from er_twin import active_events
from er_twin.discharge_coord import ResolveFlow
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
                dctx.ctx,
                dctx.cmd.sender,
                f'Current events:\n{listing}\nReply "resolve evt-0001" to close one.',
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
            await dctx.send_chat(
                dctx.ctx, dctx.cmd.sender, f"Event {event_id} not found or already resolved."
            )
            return True

        event_type = rec.get("type", "event")
        patient_id = rec.get("patient_id")

        # For discharge events, route resource release through real agent messages.
        if event_type == "discharge" and patient_id:
            from er_twin.agents.orchestrator import _start_resolve_flow

            # Build the release queue: bed first, then nurses, then doctors.
            patient_rec = store.get(f"er:patient:{patient_id}")
            queue: list[dict] = []
            bed_id = patient_rec.get("assigned_bed")
            if bed_id:
                queue.append({"kind": "bed", "id": bed_id, "patient_id": patient_id})

            from er_twin.agents import nurse as nurse_mod, doctor as doctor_mod

            care_team = list(patient_rec.get("care_team", []))
            nurses = {m for m in care_team if m.startswith("nurse")}
            nurses |= {
                nid
                for nid in nurse_mod.NURSES
                if patient_id in store.get(nurse_mod.nurse_key(nid)).get("assignments", [])
            }
            doctors = {m for m in care_team if m.startswith("doc")}
            doctors |= {
                did
                for did in doctor_mod.DOCTORS
                if patient_id in store.get(doctor_mod.doctor_key(did)).get("assignments", [])
            }
            for nid in sorted(nurses):
                queue.append({"kind": "nurse", "id": nid, "patient_id": patient_id})
            for did in sorted(doctors):
                queue.append({"kind": "doctor", "id": did, "patient_id": patient_id})

            dctx.session_senders.remember(dctx.cmd.session_id, dctx.cmd.sender)
            flow = ResolveFlow(
                flow_id=dctx.cmd.flow_id,
                session_id=dctx.cmd.session_id,
                chat_sender=dctx.cmd.sender,
                event_id=event_id,
                event_type=event_type,
                patient_id=patient_id,
                release_queue=queue,
            )
            await _start_resolve_flow(dctx.ctx, flow)
            # Gate released asynchronously in _finish_resolve.
            return False

        # Non-discharge events: resolve immediately with a synchronous reply.
        msg = f"Resolved {event_id} ({event_type}) — moved to event log."
        dctx.record_memory(dctx.ctx, msg)
        await dctx.send_chat(dctx.ctx, dctx.cmd.sender, msg)
        return True


def resolve_event_from_dashboard(store, event_id: str, replay_recorder) -> dict | None:
    """Dashboard API entry point for resolving an active event.

    Writes the store directly (`release_patient_resources` for discharge). Chat resolve
    uses the uAgent BedRelease/StaffRelease pipeline instead.
    """
    rec = active_events.resolve_active_event(store, event_id, replay_recorder)
    if rec is None:
        return None
    if rec.get("type") == "discharge" and rec.get("patient_id"):
        release_patient_resources(store, rec["patient_id"])
    return rec
