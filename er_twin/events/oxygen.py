"""Low oxygen alert event handler — async uAgent messaging showcase."""

from __future__ import annotations

from er_twin import active_events
from er_twin.addresses import address_for
from er_twin.agents import equipment, nurse
from er_twin.display import display
from er_twin.events.base import DispatchContext, EventHandler
from er_twin.oxygen_coord import (
    apply_oxygen_swap,
    bed_from_text,
    cleanup_oxygen,
    format_oxygen_confirmation,
    should_start_o2_dispatch,
)
from er_twin.oxygen_flow import OxygenFlow
from er_twin.protocols import (
    EquipmentLocateRequest,
    EquipmentLocateResponse,
    LowSupplyAlert,
    SimulateOxygenDropRequest,
    StaffDispatchRequest,
    StaffDispatchResponse,
)


class OxygenHandler(EventHandler):
    key = "oxygen"
    keywords = ("oxygen is dropping", "oxygen", "o2 low", "low oxygen")
    mock_reply = "Low O2 on bed-3 (88%). Dispatched nurse-2 with replacement unit o2-2. ETA ~15s."
    incident_type = "low_oxygen_alert"
    visual_style = "urgent but non-graphic hospital operations replay showing rapid oxygen response"

    async def dispatch(self, dctx: DispatchContext) -> bool:
        if dctx.store is None:
            await dctx.send_chat(dctx.ctx, dctx.cmd.sender, self.mock_reply)
            return True
        bed_id = bed_from_text(dctx.cmd.text)
        eid = equipment.oxygen_unit_at_bed(dctx.store, bed_id)
        if eid is None:
            await dctx.send_chat(dctx.ctx, dctx.cmd.sender, f"No oxygen unit found at {display(bed_id)}.")
            return True
        dctx.session_senders.remember(dctx.cmd.session_id, dctx.cmd.sender)
        flow = OxygenFlow(
            flow_id=dctx.cmd.flow_id, bed_id=bed_id, alert_equipment_id=eid,
            session_id=dctx.cmd.session_id, chat_sender=dctx.cmd.sender,
        )
        dctx.oxygen_flows[dctx.cmd.flow_id] = flow
        dctx.record_milestone(
            flow.lines, dctx.store, "oxygen", "orchestrator", "oxygen_drop_simulated", eid, bed=bed_id,
        )
        await dctx.ctx.send(
            address_for(eid),
            SimulateOxygenDropRequest(flow_id=dctx.cmd.flow_id, bed_id=bed_id, equipment_id=eid),
        )
        return False

    async def on_low_supply(self, dctx: DispatchContext, msg: LowSupplyAlert) -> None:
        store = dctx.store
        eid = msg.equipment_id
        if not should_start_o2_dispatch(dctx.in_flight_o2_dispatches, eid):
            dctx.ctx.logger.info(f"duplicate_alert_ignored: O2 dispatch already in progress for {eid}")
            return
        flow = dctx.oxygen_flows.get(msg.flow_id) if msg.flow_id else None
        if flow is None:
            bed_id = equipment.bed_for_equipment(store, eid)
            if bed_id is None:
                dctx.ctx.logger.warning(f"LowSupplyAlert for {eid} with no locatable bed; ignoring")
                return
            flow = OxygenFlow(
                flow_id=msg.flow_id or dctx.new_flow_id("oxygen-auto"),
                bed_id=bed_id, alert_equipment_id=eid,
            )
            dctx.oxygen_flows[flow.flow_id] = flow
        flow.alert_equipment_id = eid
        dctx.in_flight_o2_dispatches[eid] = flow.flow_id
        flow.status = "locating"
        dctx.record_milestone(
            flow.lines, store, "oxygen", "equipment", "alert_raised", eid,
            supply_level=msg.supply_level, bed=flow.bed_id,
        )
        replacement = equipment.locate_replacement(store, msg.type, exclude_id=eid)
        flow.replacement_id = replacement
        if replacement is None:
            dctx.record_milestone(
                flow.lines, store, "oxygen", "equipment", "no_replacement_unit_available", eid, bed=flow.bed_id,
            )
            await self._finish(dctx, flow.flow_id, f"Low O2 on {display(flow.bed_id)}: no available replacement unit nearby.")
            return
        await dctx.ctx.send(
            address_for(replacement),
            EquipmentLocateRequest(type=msg.type, near_location=msg.location, flow_id=flow.flow_id),
        )

    async def on_locate(self, dctx: DispatchContext, msg: EquipmentLocateResponse) -> None:
        store = dctx.store
        flow = dctx.oxygen_flows.get(msg.flow_id)
        if flow is None or flow.status == "done":
            return
        if not msg.available or msg.equipment_id is None:
            await self._finish(dctx, flow.flow_id, f"Low O2 on {display(flow.bed_id)}: no available replacement unit nearby.")
            return
        flow.replacement_id = msg.equipment_id
        flow.status = "dispatching"
        dctx.record_milestone(
            flow.lines, store, "oxygen", "equipment", "unit_located", msg.equipment_id,
            location=msg.location, bed=flow.bed_id,
        )
        nurse_id = nurse.find_available_nurse(store)
        if nurse_id is None:
            dctx.record_milestone(flow.lines, store, "oxygen", "nurse", "no_dispatch_nurse_available", flow.bed_id)
            await self._finish(
                dctx, flow.flow_id,
                f"Replacement {display(msg.equipment_id)} located for {display(flow.bed_id)}, but no nurse is available.",
            )
            return
        flow.nurse_id = nurse_id
        await dctx.ctx.send(
            address_for(nurse_id),
            StaffDispatchRequest(
                task="deliver_oxygen", target_location=msg.location,
                equipment_id=msg.equipment_id, flow_id=flow.flow_id,
            ),
        )

    async def on_dispatch(self, dctx: DispatchContext, msg: StaffDispatchResponse) -> None:
        store = dctx.store
        flow = dctx.oxygen_flows.get(msg.flow_id)
        if flow is None or flow.status == "done":
            return
        nurse_id = flow.nurse_id or msg.staff_id
        if not msg.accepted:
            dctx.record_milestone(flow.lines, store, "oxygen", "nurse", "no_dispatch_nurse_available", flow.bed_id, nurse=nurse_id)
            await self._finish(dctx, flow.flow_id, f"{display(nurse_id)} declined the oxygen dispatch for {display(flow.bed_id)}.")
            return
        flow.status = "done"
        dctx.record_milestone(flow.lines, store, "oxygen", "nurse", "nurse_dispatched", nurse_id, bed=flow.bed_id, equipment=flow.replacement_id)
        apply_oxygen_swap(store, flow.alert_equipment_id, flow.replacement_id, flow.bed_id, nurse_id)
        dctx.record_milestone(
            flow.lines, store, "oxygen", "orchestrator", "oxygen_swap_complete", flow.bed_id,
            depleted=flow.alert_equipment_id, replacement=flow.replacement_id, nurse=nurse_id,
        )
        reply = format_oxygen_confirmation(flow.bed_id, flow.replacement_id, nurse_id)
        await self._finish(dctx, flow.flow_id, reply)

    async def _finish(self, dctx: DispatchContext, flow_id: str, reply: str) -> None:
        store = dctx.store
        flow = dctx.oxygen_flows.get(flow_id)
        gated = bool(flow and flow.chat_sender)
        incident_id: str | None = None
        if flow is not None and store is not None:
            if flow.status == "done":
                dctx.record_milestone(flow.lines, store, "oxygen", "orchestrator", "oxygen_event_complete", flow.bed_id)
            incident_id = dctx.emit_replay(dctx.ctx, "oxygen", flow.lines)
            evt_id = active_events.create_active_event(
                store, "oxygen", reply,
                incident_id=incident_id or "", flow_id=flow_id,
            )
            reply = f"{reply}\nCurrent event {evt_id} — resolve when complete."
        dctx.record_memory(dctx.ctx, reply)
        if flow and flow.chat_sender:
            await dctx.send_chat(dctx.ctx, flow.chat_sender, reply)
        cleanup_oxygen(flow_id, dctx.oxygen_flows, dctx.in_flight_o2_dispatches, dctx.session_senders)
        if gated:
            await dctx.complete_command(dctx.ctx, flow_id)
