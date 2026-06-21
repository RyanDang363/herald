"""Ping skeleton event — stub round-trip."""

from __future__ import annotations

from er_twin.addresses import STUB_ADDRESS
from er_twin.events.base import DispatchContext, EventHandler
from er_twin.protocols import PingRequest


class PingHandler(EventHandler):
    key = "ping"
    keywords = ("ping",)
    mock_reply = ""
    incident_type = ""
    visual_style = ""

    async def dispatch(self, dctx: DispatchContext) -> bool:
        dctx.session_senders.remember(dctx.cmd.session_id, dctx.cmd.sender)
        dctx.pending_ping_sessions.append((dctx.cmd.flow_id, dctx.cmd.session_id))
        await dctx.ctx.send(STUB_ADDRESS, PingRequest(text=dctx.cmd.text))
        return False
