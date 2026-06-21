"""MRN-driven interactive intake event handler."""

from __future__ import annotations

from er_twin import active_events, replay
from er_twin.display import display
from er_twin.events.base import DispatchContext, EventHandler, PendingProposal
from er_twin.events.helpers import (
    ehr_name_for_mrn,
    extract_complaint,
    extract_mrn,
    format_proposal,
    is_confirm,
    normalize_text,
    parse_assignment_override,
    synthesize_vitals,
)
from er_twin.events.intake_flow import commit_full_intake, plan_intake_proposal


class IntakeHandler(EventHandler):
    key = "intake"
    keywords = ("patient intake", "admit patient", "new patient arrived", "chest pain", "new patient")
    mock_reply = (
        "Please provide the patient MRN (e.g. MRN-0005) to begin intake. "
        "After triage I will propose bed, nurse, and doctor assignments for your confirmation."
    )
    incident_type = "patient_intake"
    visual_style = "clean cinematic ER intake and triage replay, realistic hospital operations"

    async def dispatch(self, dctx: DispatchContext) -> bool:
        if dctx.store is None:
            await dctx.send_chat(dctx.ctx, dctx.cmd.sender, self.mock_reply)
            return True
        return await self._start_intake(dctx, dctx.cmd.text)

    async def resume(self, dctx: DispatchContext, pending: PendingProposal) -> bool:
        if pending.kind == "awaiting_mrn":
            return await self._handle_mrn(dctx, pending, dctx.cmd.text)
        if pending.kind == "awaiting_complaint":
            return await self._handle_complaint(dctx, pending, dctx.cmd.text)
        if pending.kind == "intake_confirm":
            return await self._handle_confirm(dctx, pending, dctx.cmd.text)
        return True

    async def _start_intake(self, dctx: DispatchContext, text: str) -> bool:
        mrn = extract_mrn(text)
        if not mrn:
            pending = PendingProposal(
                kind="awaiting_mrn", event_type="intake",
                sender=dctx.cmd.sender, session_id=dctx.cmd.session_id,
            )
            dctx.session_pending[dctx.cmd.session_id] = pending
            await dctx.send_chat(
                dctx.ctx, dctx.cmd.sender,
                "Please provide the patient MRN (e.g. MRN-0005) to begin intake.",
                end_session=False,
            )
            return True
        complaint = extract_complaint(text, mrn)
        if not complaint:
            pending = PendingProposal(
                kind="awaiting_complaint", event_type="intake",
                sender=dctx.cmd.sender, session_id=dctx.cmd.session_id, mrn=mrn,
                name=ehr_name_for_mrn(mrn), vitals=synthesize_vitals(mrn),
            )
            dctx.session_pending[dctx.cmd.session_id] = pending
            await dctx.send_chat(
                dctx.ctx, dctx.cmd.sender,
                f"MRN {mrn} ({pending.name}) noted. What is the chief complaint?",
                end_session=False,
            )
            return True
        return await self._propose(dctx, mrn, ehr_name_for_mrn(mrn), complaint, synthesize_vitals(mrn))

    async def _handle_mrn(self, dctx: DispatchContext, pending: PendingProposal, text: str) -> bool:
        mrn = extract_mrn(text) or normalize_text(text).upper()
        if not mrn.startswith("MRN-"):
            await dctx.send_chat(
                dctx.ctx, pending.sender,
                "I need a valid MRN (e.g. MRN-0005). Please try again.",
                end_session=False,
            )
            return True
        complaint = extract_complaint(text, mrn)
        name = ehr_name_for_mrn(mrn)
        vitals = synthesize_vitals(mrn)
        dctx.session_pending.pop(pending.session_id, None)
        if not complaint:
            dctx.session_pending[pending.session_id] = PendingProposal(
                kind="awaiting_complaint", event_type="intake",
                sender=pending.sender, session_id=pending.session_id,
                mrn=mrn, name=name, vitals=vitals,
            )
            await dctx.send_chat(
                dctx.ctx, pending.sender,
                f"MRN {mrn} ({name}) noted. What is the chief complaint?",
                end_session=False,
            )
            return True
        return await self._propose(dctx, mrn, name, complaint, vitals, pending.session_id, pending.sender)

    async def _handle_complaint(self, dctx: DispatchContext, pending: PendingProposal, text: str) -> bool:
        complaint = extract_complaint(text, pending.mrn) or normalize_text(text)
        if len(complaint) < 3:
            await dctx.send_chat(
                dctx.ctx, pending.sender,
                "Please describe the chief complaint (e.g. chest pain, ankle injury).",
                end_session=False,
            )
            return True
        dctx.session_pending.pop(pending.session_id, None)
        return await self._propose(
            dctx, pending.mrn, pending.name, complaint, pending.vitals,
            pending.session_id, pending.sender,
        )

    async def _propose(
        self, dctx: DispatchContext, mrn: str, name: str, complaint: str, vitals: dict,
        session_id: str | None = None, sender: str | None = None,
    ) -> bool:
        store = dctx.store
        assert store is not None
        sid = session_id or dctx.cmd.session_id
        user = sender or dctx.cmd.sender
        plan = plan_intake_proposal(store, name, complaint, vitals, mrn)
        if plan.get("error") == "duplicate":
            await dctx.send_chat(dctx.ctx, user, f"{name} ({mrn}) is already active in the ER.")
            return True
        if plan.get("error") == "patient_capacity_reached":
            await dctx.send_chat(dctx.ctx, user, f"{name} is waiting — patient capacity reached.")
            return True
        proposed = plan["proposed"]
        available = plan.get("available") or {}

        # Register a pending_approval active event so the dashboard can show the proposal card.
        # No patient_id yet — it is created on confirm (nothing is written to the store until then).
        evt_id = active_events.create_active_event(
            store,
            "intake_proposal",
            f"Awaiting assignment — {plan['name']} ({mrn}) ESI-{plan['acuity']}",
            patient_id="",
            status="pending_approval",
            extra_data={
                "mrn": mrn,
                "name": plan["name"],
                "acuity": plan["acuity"],
                "specialty": plan["specialty"],
                "chief_complaint": complaint,
                "vitals": vitals,
                "proposed": proposed,
                "available": available,
            },
        )

        pending = PendingProposal(
            kind="intake_confirm", event_type="intake",
            sender=user, session_id=sid, mrn=mrn, name=plan["name"],
            chief_complaint=complaint, vitals=vitals, patient_id="",
            acuity=plan["acuity"], specialty=plan["specialty"], proposed=proposed,
            active_event_id=evt_id,
        )
        dctx.session_pending[sid] = pending
        msg = format_proposal(
            plan["name"], mrn, plan["acuity"], plan["specialty"],
            proposed["bed_id"], proposed["nurse_id"], proposed["doctor_id"], display,
            available=available,
        )
        await dctx.send_chat(dctx.ctx, user, msg, end_session=False)
        return True

    async def _handle_confirm(self, dctx: DispatchContext, pending: PendingProposal, text: str) -> bool:
        store = dctx.store
        assert store is not None
        proposed = dict(pending.proposed)
        if not is_confirm(text):
            override = parse_assignment_override(text)
            if any(override.values()):
                proposed.update({k: v for k, v in override.items() if v})
            else:
                await dctx.send_chat(
                    dctx.ctx, pending.sender,
                    'Reply "confirm" to accept the proposal, or "assign doc1 nurse2 bed3" to override.',
                    end_session=False,
                )
                return True
        dctx.session_pending.pop(pending.session_id, None)
        lines: list[dict] = []

        def capture(action, target, detail):
            dctx.record_milestone(
                lines, store, "intake", replay.actor_for(action), action, target, **detail,
            )

        dctx.record_milestone(lines, store, "intake", "orchestrator", "intake_received", None, mrn=pending.mrn)
        # Patient record is created here for the first time (deferred from plan phase).
        outcome = commit_full_intake(
            store, pending.name, pending.chief_complaint, pending.vitals, pending.mrn,
            proposed.get("bed_id"), proposed.get("nurse_id"), proposed.get("doctor_id"),
            on_milestone=capture,
        )
        if outcome.get("error") in ("duplicate", "patient_capacity_reached"):
            await dctx.send_chat(dctx.ctx, pending.sender, outcome["confirmation"])
            return True

        patient_id = outcome["patient_id"]
        incident_id = dctx.emit_replay(dctx.ctx, "intake", lines)

        # Promote the pending_approval event to active and stamp the now-known patient_id.
        if pending.active_event_id:
            promoted = active_events.confirm_pending_proposal(
                store, pending.active_event_id, outcome["confirmation"], new_type="intake",
            )
            if promoted:
                from er_twin.active_events import _event_key
                store.update(_event_key(pending.active_event_id), {"patient_id": patient_id})
            evt_id = pending.active_event_id if promoted else active_events.create_active_event(
                store, "intake", outcome["confirmation"],
                patient_id=patient_id, incident_id=incident_id or "",
            )
        else:
            evt_id = active_events.create_active_event(
                store, "intake", outcome["confirmation"],
                patient_id=patient_id, incident_id=incident_id or "",
            )

        dctx.record_memory(dctx.ctx, outcome["confirmation"])
        await dctx.send_chat(
            dctx.ctx, pending.sender,
            f"{outcome['confirmation']}\nCurrent event {evt_id} — resolve when complete.",
        )
        return True
