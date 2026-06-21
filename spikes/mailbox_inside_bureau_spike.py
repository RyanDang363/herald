"""SPIKE (throwaway research, not P1 code): can a mailbox=True Orchestrator run *inside* a Bureau
alongside a private local StubAgent, and still exchange in-process messages?

Run:  .venv/Scripts/python.exe spikes/mailbox_inside_bureau_spike.py
It self-terminates: prints ROUND-TRIP OK and exits 0 on success, or hard-exits after a watchdog
timeout. No ASI:One / Redis / Pika. Reuses the real PingRequest/PingResponse models.
"""

import os
import threading

from uagents import Agent, Bureau, Context
from er_twin.protocols import PingRequest, PingResponse

# Hard watchdog so the spike never hangs the terminal.
threading.Timer(20.0, lambda: (print("WATCHDOG: 20s elapsed, exiting"), os._exit(2))).start()

orchestrator = Agent(name="spike-orch", seed="spike-orchestrator-seed", mailbox=True)
stub = Agent(name="spike-stub", seed="spike-stub-seed")

STUB_ADDRESS = stub.address
print(f"orchestrator.address = {orchestrator.address}")
print(f"stub.address         = {STUB_ADDRESS}")
print(f"orchestrator.mailbox_client is None? {orchestrator.mailbox_client is None}")


@orchestrator.on_event("startup")
async def kick(ctx: Context):
    ctx.logger.info("orchestrator startup -> sending PingRequest to stub")
    await ctx.send(STUB_ADDRESS, PingRequest(text="ping from orchestrator"))


@stub.on_message(PingRequest)
async def on_ping(ctx: Context, sender: str, msg: PingRequest):
    ctx.logger.info(f"stub received PingRequest({msg.text!r}) from {sender[:12]}… -> replying")
    await ctx.send(sender, PingResponse(text=f"pong: {msg.text}", agent_id="spike-stub"))


@orchestrator.on_message(PingResponse)
async def on_pong(ctx: Context, sender: str, msg: PingResponse):
    ctx.logger.info(f"orchestrator received PingResponse({msg.text!r}) from agent_id={msg.agent_id}")
    print("ROUND-TRIP OK: in-process Bureau messaging works with a mailbox orchestrator")
    os._exit(0)


bureau = Bureau()
bureau.add(orchestrator)
bureau.add(stub)

if __name__ == "__main__":
    print("starting Bureau (mailbox orchestrator + private stub)…")
    bureau.run()
