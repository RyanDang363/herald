"""SPIKE (throwaway proof, not shipped code): does the Phase-4 low-oxygen event actually round-trip
as REAL async uAgent messaging through the live Bureau — EquipmentAgent autonomously emitting
`LowSupplyAlert`, then Orchestrator alert → locate → dispatch → swap across separate handlers?

This is the proof behind the OXY-* pure-function tests: those verify the logic, this verifies the
wiring under a running Bureau (which is flaky to drive from pytest on Windows, so it lives here).

A throwaway trigger agent stands in for the chat command: on startup it sends one
`SimulateOxygenDropRequest` to the bed-3 oxygen unit's address — exactly what the Orchestrator's chat
handler does. The chain then runs agent-to-agent. The trigger polls the shared store and prints
SWAP OK + exits 0 once the swap lands, or the watchdog hard-exits.

Run:  .venv/Scripts/python.exe spikes/oxygen_async_flow_spike.py
"""

import os
import threading

from uagents import Agent, Bureau, Context

from er_twin.addresses import address_for, seed_for
from er_twin.agents import orchestrator as orch
from er_twin.agents.orchestrator import orchestrator
from er_twin.main import seed_baseline, seed_state
from er_twin.protocols import SimulateOxygenDropRequest
from er_twin.storage import InMemoryStore

threading.Timer(25.0, lambda: (print("WATCHDOG: 25s elapsed, FAIL"), os._exit(2))).start()

store = InMemoryStore()
seed_state(store)
seed_baseline(store)  # p2 on bed3 w/ o2_1 (supply 55), nurse1 busy -> nurse2 is the dispatch pick
orch.set_store(store)

O2_1_ADDRESS = address_for("o2_1")
trigger = Agent(name="spike-oxy-trigger", seed=seed_for("spike-oxy-trigger"), network="testnet")


@trigger.on_event("startup")
async def kick(ctx: Context):
    ctx.logger.info(f"trigger -> SimulateOxygenDropRequest(bed3) to o2_1 @ {O2_1_ADDRESS[:12]}…")
    # flow_id stands in for the chat-minted id; the orchestrator treats it as an autonomous (ungated)
    # flow since it didn't originate the command — exercises the flow_id-keyed context end-to-end.
    await ctx.send(
        O2_1_ADDRESS,
        SimulateOxygenDropRequest(flow_id="spike-1", bed_id="bed3", equipment_id="o2_1"),
    )


@trigger.on_interval(period=1.0)
async def check(ctx: Context):
    o2_2 = store.get("er:equipment:o2_2")
    if o2_2.get("in_use_by") == "p2" and o2_2.get("location") == "bed-3":
        bed3 = store.get("er:bed:bed3")
        nurse2 = store.get("er:nurse:nurse2")
        p2 = store.get("er:patient:p2")
        o2_1 = store.get("er:equipment:o2_1")
        print("SWAP OK: real async oxygen flow completed end-to-end")
        print(f"  o2_2.in_use_by={o2_2.get('in_use_by')} location={o2_2.get('location')}")
        print(f"  o2_1.in_use_by={o2_1.get('in_use_by')} needs_restock={o2_1.get('needs_restock')}")
        print(f"  bed3.equipment={bed3.get('equipment')}  p2.spo2={p2.get('vitals', {}).get('spo2')}")
        print(f"  nurse2.available={nurse2.get('available')} location={nurse2.get('location')}")
        print(f"  in_flight_o2_dispatches={orch.in_flight_o2_dispatches}")  # should be cleared
        os._exit(0)


# The real entity agents that participate in the flow (equipment + nurse) plus the rest for parity.
from er_twin.agents import admissions, bed, doctor, equipment, nurse, patient, triage  # noqa: E402

bureau = Bureau()
bureau.add(orchestrator)
for module in (patient, bed, nurse, doctor, equipment, admissions, triage):
    for agent in module.build_agents(store):
        bureau.add(agent)
bureau.add(trigger)

if __name__ == "__main__":
    print("starting Bureau (orchestrator + entity agents + oxygen trigger)…")
    bureau.run()
