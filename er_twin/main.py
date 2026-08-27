"""Single entry point for the ER Twin (LLD §5).

Builds ONE `Bureau` holding the public OrchestratorAgent (mailbox + Chat Protocol, reachable from
ASI:One) and every private entity agent — the PatientAgent pool plus the bed / nurse / doctor /
equipment / admissions / triage agents — then runs both the Bureau AND the admin dashboard on the
same asyncio event loop (ORCH-SYS-001).

Co-hosting model (default):
  - Bureau: manages all uAgent message handling and mailbox polling.
  - Dashboard: FastAPI/uvicorn scheduled on the Bureau's event loop (create_task + bureau.run).
  - Shared store: injected into both so the dashboard reads live agent state.
  - Commands enter through ASI:One chat (or USE_MOCK keyword routing), not the dashboard.

All agents share one `InMemoryStore` (the demo-safe default behind `StorageInterface`). State is
seeded deterministically before the Bureau runs (no async startup race): `seed_state` lays the clean
inventory, then `seed_baseline` adds the mid-shift demo scenario so the oxygen and summary commands
are demoable in any order.

Run:
  USE_MOCK=true uv run python -m er_twin.main          # Bureau + dashboard co-hosted
  USE_MOCK=true uv run python -m er_twin.main --no-dashboard  # Bureau only
  uvicorn dashboard.server:app --port 8050             # Dashboard standalone (fixture source)

Expected on startup: the Orchestrator logs its `agent1q…` address plus an Agentverse inspector URL.
A line like "Agent mailbox not found: create one using the agent inspector" is EXPECTED until the
one-time inspector connect — it is not a failure.
"""

import argparse
import asyncio

import uvicorn
from uagents import Bureau

from er_twin.addresses import ORCHESTRATOR_ADDRESS, STUB_ADDRESS
from er_twin.agents import admissions, bed, doctor, equipment, nurse, patient, triage
from er_twin.agents import orchestrator as orch
from er_twin.agents.orchestrator import orchestrator
from er_twin.agents.stub import stub
from er_twin.config import settings
from er_twin.memory import make_memory
from er_twin.storage import StorageInterface, make_store

# Modules that seed a slice of the shared store (have init_state). Order is irrelevant.
_ENTITY_MODULES = (patient, bed, nurse, doctor, equipment)
# Modules contributing agents but no seeded inventory (handlers call domain fns on demand).
_AGENT_ONLY_MODULES = (admissions, triage)


def seed_state(store: StorageInterface) -> None:
    """Seed every entity's clean initial inventory into the shared store (deterministic, pre-run)."""
    for module in _ENTITY_MODULES:
        module.init_state(store)


def _inventory_counts(store: StorageInterface) -> dict[str, int]:
    """Read back the live index sets so the boot banner reports what actually landed in the store
    (not the module constants), exposing a partial/failed seed instead of hiding it."""
    return {e: len(store.list_ids(e)) for e in ("patient", "bed", "nurse", "doctor", "equipment")}


def ensure_seeded(store: StorageInterface) -> dict[str, int]:
    """Seed the store, verify the core inventory landed, and re-seed once if it did not.

    With the demo-default `InMemoryStore` the seed is always durable. With a persistent `RedisStore`
    it must not be assumed: a prior/parallel run or a transient backend error can leave the keyspace
    without beds/nurses, after which the Orchestrator answers every intake with `no_bed_available`
    while the boot log still looks healthy. So we seed, read the indexes back, and retry once if beds
    or nurses are missing — turning a silent downstream failure into a loud, self-healing startup step.
    Returns the verified counts for the boot banner.
    """
    seed_state(store)
    seed_baseline(store)
    counts = _inventory_counts(store)
    if counts["bed"] == 0 or counts["nurse"] == 0:
        seed_state(store)
        seed_baseline(store)
        counts = _inventory_counts(store)
    return counts


def seed_baseline(store: StorageInterface) -> None:
    """Layer the mid-shift demo scenario on top of the clean seed (decision Gap 5 / R2-B/C).

    p1 waiting-room patient, p2 on bed-3 with oxygen unit o2_1; nurse1 busy with p2 (so the oxygen
    dispatch deterministically picks nurse2); doc2 carrying p2. Patient counter advanced to 2.
    """
    store.set("er:counter:patient", {"value": 2})
    store.set(
        "er:patient:p1",
        {
            "id": "p1",
            "mrn": "MRN-0001",
            "name": "Sam Rivera",
            "chief_complaint": "observation after minor fall",
            "acuity": 4,
            "specialty": "general",
            "status": "in_triage",
            "vitals": {
                "heart_rate": 84,
                "blood_pressure": "128/78",
                "resp_rate": 16,
                "spo2": 98,
                "temperature_f": 98.4,
                "pain_score": 3,
            },
            "assigned_bed": None,
            "care_team": [],
        },
    )
    store.set(
        "er:patient:p2",
        {
            "id": "p2",
            "mrn": "MRN-0002",
            "name": "Avery Chen",
            "chief_complaint": "shortness of breath",
            "acuity": 3,
            "specialty": "general",
            "status": "in_treatment",
            "vitals": {
                "heart_rate": 104,
                "blood_pressure": "136/84",
                "resp_rate": 24,
                "spo2": 92,
                "temperature_f": 99.1,
                "pain_score": 4,
            },
            "assigned_bed": "bed3",
            "care_team": ["nurse1", "doc2"],
        },
    )
    store.update("er:bed:bed3", {"occupied_by": "p2", "status": "occupied", "equipment": ["o2_1"]})
    store.update("er:equipment:o2_1", {"supply_level": 55, "in_use_by": "p2", "location": "bed-3"})
    store.update(
        "er:nurse:nurse1", {"available": False, "location": "bed-3", "assignments": ["p2"]}
    )
    store.update("er:doctor:doc2", {"load": 1, "assignments": ["p2"]})


def build_bureau(store: StorageInterface) -> Bureau:
    bureau = Bureau()
    bureau.add(orchestrator)
    bureau.add(stub)
    for module in (*_ENTITY_MODULES, *_AGENT_ONLY_MODULES):
        for agent in module.build_agents(store):
            bureau.add(agent)
    return bureau


def _print_banner(store: StorageInterface, counts: dict[str, int]) -> None:
    print(f"USE_MOCK             = {settings.use_mock}")
    print(f"store                = {type(store).__name__}")
    print(f"orchestrator.address = {ORCHESTRATOR_ADDRESS}")
    print(f"stub.address         = {STUB_ADDRESS}")
    print(
        f"entity agents        = {patient.PATIENT_COUNT} patients, {len(bed.BEDS)} beds, "
        f"{len(nurse.NURSES)} nurses, {len(doctor.DOCTORS)} doctors, "
        f"{len(equipment.EQUIPMENT)} equipment, +admissions +triage"
    )
    print(
        f"inventory (in store) = {counts['patient']} patients, {counts['bed']} beds, "
        f"{counts['nurse']} nurses, {counts['doctor']} doctors, {counts['equipment']} equipment"
    )
    if counts["bed"] == 0 or counts["nurse"] == 0:
        print(
            "WARNING: core inventory (beds/nurses) missing after seed — intakes will report "
            "no_bed_available. Check REDIS_URL / backend connectivity before demoing."
        )


async def _run_dashboard(host: str = "0.0.0.0", port: int | None = None) -> None:
    """Run the FastAPI dashboard as an ASGI app on the current event loop."""
    from dashboard.server import app

    cfg = uvicorn.Config(
        app,
        host=host,
        port=port or settings.dashboard_port,
        log_level="warning",
    )
    server = uvicorn.Server(cfg)
    await server.serve()


def _connect_mailbox() -> None:
    """One-time mailbox bootstrap: run the Orchestrator standalone so the Agentverse Inspector
    can connect a mailbox to its address.  Stop with Ctrl-C once the Inspector confirms success.

    Background: the Inspector does not support connecting a mailbox while a Bureau is running,
    so this command launches the same OrchestratorAgent (identical seed → identical address)
    in standalone mode.  The Bureau run afterwards reuses the persisted mailbox automatically.
    """
    from er_twin.agents.orchestrator import orchestrator as _orch

    print(f"Mailbox bootstrap — agent address: {_orch.address}")
    print("Open the Agentverse Inspector, Connect → Mailbox, then stop this (Ctrl-C) and run main.")
    _orch.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="ER Twin Bureau")
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Run Bureau only, without the co-hosted admin dashboard.",
    )
    parser.add_argument(
        "--connect-mailbox",
        action="store_true",
        help="One-time mailbox bootstrap: run the Orchestrator standalone for Agentverse Inspector.",
    )
    args = parser.parse_args()

    if args.connect_mailbox:
        _connect_mailbox()
        return

    # Backend selection: USE_MOCK=true ⇒ InMemoryStore + NoopMemory; USE_MOCK=false with
    # REDIS_URL / AGENT_MEMORY_* ⇒ live Redis + Iris.
    store = make_store()
    memory = make_memory()
    counts = ensure_seeded(store)
    orch.set_store(store)
    orch.set_memory(memory)

    # Inject the shared store into the dashboard datasource so /api/state reads live state.
    from dashboard import datasource

    datasource.set_live_store(store)

    _print_banner(store, counts)

    bureau = build_bureau(store)

    if args.no_dashboard:
        print("dashboard            = disabled (--no-dashboard)")
        try:
            bureau.run()
        finally:
            memory.close()
        return

    print(
        f"dashboard            = http://0.0.0.0:{settings.dashboard_port} "
        f"(source={settings.dashboard_source})"
    )

    # Co-host on the Bureau's event loop — do NOT asyncio.run(bureau.run_async()).
    # Bureau (and each Agent) captures a loop at construction via get_event_loop();
    # asyncio.run() would create a second loop and fail with
    # "Future attached to a different loop".
    loop = asyncio.get_event_loop_policy().get_event_loop()
    loop.create_task(_run_dashboard(port=settings.dashboard_port))
    try:
        bureau.run()
    finally:
        memory.close()


if __name__ == "__main__":
    main()
