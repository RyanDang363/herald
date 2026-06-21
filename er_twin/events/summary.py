"""Read-only status summary — never logged to current events or replay."""

from __future__ import annotations

from er_twin.status_summary import compose_summary
from er_twin.events.base import DispatchContext, EventHandler


class SummaryHandler(EventHandler):
    key = "summary"
    keywords = ("what's happening in the er", "show me what", "status summary")
    mock_reply = "3 patients active, 2 beds occupied, 1 nurse free. No critical alerts."
    incident_type = "er_status_summary"
    visual_style = "clean hospital command-center status visualization"
    logs_to_replay = False

    async def dispatch(self, dctx: DispatchContext) -> bool:
        if dctx.store is None:
            await dctx.send_chat(dctx.ctx, dctx.cmd.sender, self.mock_reply)
            return True
        alert_beds = [
            dctx.oxygen_flows[fid].bed_id
            for fid in dctx.in_flight_o2_dispatches.values()
            if fid in dctx.oxygen_flows
        ]
        recalled = dctx.recall_memory("recent ER patients, admissions, and alerts")
        summary = compose_summary(dctx.store, alert_beds, recalled)
        dctx.record_memory(dctx.ctx, summary)
        await dctx.send_chat(dctx.ctx, dctx.cmd.sender, summary)
        return True
