"""StubAgent — the minimal private Bureau agent for the Phase 1 skeleton.

Stands in for the entity agents that arrive in Phase 2. It has no mailbox (private, in-process
only) and its only behavior is to answer a `PingRequest` with a `PingResponse`, proving the
in-process Orchestrator → entity → Orchestrator loop (ORCH-SKEL-001). Its address is seed-derived
(ORCH-SYS-002) and matches `addresses.STUB_ADDRESS`.
"""

from uagents import Agent, Context

from er_twin.addresses import seed_for
from er_twin.protocols import PingRequest, PingResponse

STUB_AGENT_ID = "stub"

stub = Agent(name="er-stub", seed=seed_for(STUB_AGENT_ID), network="testnet")


@stub.on_message(PingRequest)
async def on_ping(ctx: Context, sender: str, msg: PingRequest):
    # @spec ORCH-SKEL-001 — reply in-process so the Orchestrator can relay it back to chat.
    ctx.logger.info(f"PingRequest({msg.text!r}) from {sender[:12]}… -> replying pong")
    await ctx.send(sender, PingResponse(text=f"pong: {msg.text}", agent_id=STUB_AGENT_ID))
