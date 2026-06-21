"""Discharge (outtake) event handler — MRN keyed, propose sign-off then resolve to free resources."""

from __future__ import annotations

from er_twin import active_events
from er_twin.display import display
from er_twin.events.base import DispatchContext, EventHandler, PendingProposal
from er_twin.events.discharge_flow import commit_discharge, plan_discharge_proposal
from er_twin.events.helpers import (
    extract_mrn,
    format_discharge_proposal,
    is_confirm,
    normalize_text,
    parse_assignment_override,
)


class DischargeHandler(EventHandler):
    key = "discharge"
    keywords = ("discharge patient", "patient discharge", "outtake", "ready to go home", "discharge")
    mock_reply = "Please provide the patient MRN (e.g. MRN-0002) to begin discharge."
    incident_type = "patient_discharge"
    visual_style = "calm, resolved ER discharge sequence"

    async def dispatch(self, dctx: DispatchContext) -> bool:
        if dctx.store is None:
            await dctx.send_chat(dctx.ctx, dctx.cmd.sender, self.mock_reply)
            return True
        mrn = extract_mrn(dctx.cmd.text)
        if not mrn:
            dctx.session_pending[dctx.cmd.session_id] = PendingProposal(
                kind="awaiting_mrn", event_type="discharge",
                sender=dctx.cmd.sender, session_id=dctx.cmd.session_id,
            )
            await dctx.send_chat(
                dctx.ctx, dctx.cmd.sender,
                "Please provide the patient MRN to discharge.",
                end_session=False,
            )
            return True
        return await self._propose_discharge(dctx, mrn)

    async def resume(self, dctx: DispatchContext, pending: PendingProposal) -> bool:
        if pending.kind == "awaiting_mrn":
            mrn = extract_mrn(dctx.cmd.text) or normalize_text(dctx.cmd.text).upper()
            if not mrn.startswith("MRN-"):
                await dctx.send_chat(
                    dctx.ctx, pending.sender,
                    "I need a valid MRN (e.g. MRN-0002). Please try again.",
                    end_session=False,
                )
                return True
            dctx.session_pending.pop(pending.session_id, None)
            return await self._propose_discharge(dctx, mrn, pending.sender, pending.session_id)
        if pending.kind == "discharge_confirm":
            return await self._confirm_discharge(dctx, pending, dctx.cmd.text)
        return True

    async def _propose_discharge(
        self, dctx: DispatchContext, mrn: str,
        sender: str | None = None, session_id: str | None = None,
    ) -> bool:
        store = dctx.store
        assert store is not None
        user = sender or dctx.cmd.sender
        sid = session_id or dctx.cmd.session_id
        plan = plan_discharge_proposal(store, mrn)
        if plan.get("error") == "not_found":
            await dctx.send_chat(dctx.ctx, user, f"No active patient found for {mrn}.")
            return True

        proposed = plan["proposed"]
        available = plan.get("available") or {}
        bed_id = plan.get("bed_id")

        evt_id = active_events.create_active_event(
            store,
            "discharge_proposal",
            f"Awaiting discharge sign-off — {plan['name']} ({mrn})",
            patient_id=plan["patient_id"],
            status="pending_approval",
            extra_data={
                "mrn": mrn,
                "name": plan["name"],
                "bed_id": bed_id,
                "proposed": proposed,
                "available": available,
            },
        )

        pending = PendingProposal(
            kind="discharge_confirm", event_type="discharge",
            sender=user, session_id=sid, mrn=mrn, name=plan["name"],
            patient_id=plan["patient_id"], proposed=proposed,
            active_event_id=evt_id,
        )
        dctx.session_pending[sid] = pending
        msg = format_discharge_proposal(
            plan["name"], mrn, bed_id,
            proposed.get("nurse_id"), proposed.get("doctor_id"),
            display, available=available,
        )
        await dctx.send_chat(dctx.ctx, user, msg, end_session=False)
        return True

    async def _confirm_discharge(self, dctx: DispatchContext, pending: PendingProposal, text: str) -> bool:
        store = dctx.store
        assert store is not None
        proposed = dict(pending.proposed)
        if not is_confirm(text):
            override = parse_assignment_override(text)
            if override.get("nurse_id") or override.get("doctor_id"):
                if override.get("nurse_id"):
                    proposed["nurse_id"] = override["nurse_id"]
                if override.get("doctor_id"):
                    proposed["doctor_id"] = override["doctor_id"]
            else:
                await dctx.send_chat(
                    dctx.ctx, pending.sender,
                    'Reply "confirm" to discharge, or "assign nurse2 doc1" to override sign-off staff.',
                    end_session=False,
                )
                return True

        dctx.session_pending.pop(pending.session_id, None)
        outcome = commit_discharge(
            store, pending.patient_id,
            proposed.get("nurse_id"), proposed.get("doctor_id"),
        )

        if pending.active_event_id:
            promoted = active_events.confirm_pending_proposal(
                store, pending.active_event_id, outcome["confirmation"], new_type="discharge",
            )
            evt_id = pending.active_event_id if promoted else active_events.create_active_event(
                store, "discharge", outcome["confirmation"], patient_id=pending.patient_id,
            )
        else:
            evt_id = active_events.create_active_event(
                store, "discharge", outcome["confirmation"], patient_id=pending.patient_id,
            )

        dctx.record_memory(dctx.ctx, outcome["confirmation"])
        await dctx.send_chat(
            dctx.ctx, pending.sender,
            f"{outcome['confirmation']}\nCurrent event {evt_id} — resolve to free bed and staff.",
        )
        return True
