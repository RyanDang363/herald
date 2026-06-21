"""EquipmentAgent pool (LLD §2 Equipment).

One agent per unit; state lives in `er:equipment:{id}`. Availability is type-dependent (LLD §2):
consumables (`oxygen`) track a 0–100 `supply_level` and are "low" below the threshold; devices
(`defibrillator`, `iv_pump`) leave `supply_level` null and use `in_use_by` for availability.

Phase 2 seeded the inventory and the low-supply / availability checks. Phase 4 (Event 2 — the
mandatory async showcase) adds the oxygen flow: on a scripted `SimulateOxygenDropRequest` the unit's
agent lowers its own `supply_level` below threshold (and the bed patient's spo2) and **autonomously
emits `LowSupplyAlert`** to the Orchestrator (OXY-FLOW-007 → OXY-FLOW-001); an `EquipmentLocateRequest`
asks a unit whether it can serve as a replacement (OXY-FLOW-003). The pure functions below carry the
logic (simulate drop, locate selection, swap mutation) so they unit-test against an `InMemoryStore`;
the `@on_message` handlers are thin wrappers.
"""

from uagents import Agent, Context

from er_twin.addresses import ORCHESTRATOR_ADDRESS, seed_for
from er_twin.protocols import (
    EquipmentLocateRequest,
    EquipmentLocateResponse,
    LowSupplyAlert,
    SimulateOxygenDropRequest,
)
from er_twin.storage import StorageInterface

LOW_SUPPLY_THRESHOLD = 50  # percent; oxygen below this is "low" (OXY-FLOW-001)

# Demo inventory (matches the shared fixture in docs/TEAM.md); all units start free.
EQUIPMENT: list[dict] = [
    {"id": "o2_1", "type": "oxygen", "supply_level": 45, "in_use_by": None, "location": "storage"},
    {"id": "o2_2", "type": "oxygen", "supply_level": 88, "in_use_by": None, "location": "storage"},
    {"id": "defib_1", "type": "defibrillator", "supply_level": None, "in_use_by": None, "location": "nurses-station"},
]


def equipment_key(equipment_id: str) -> str:
    return f"er:equipment:{equipment_id}"


def bed_key(bed_id: str) -> str:
    return f"er:bed:{bed_id}"


def patient_key(patient_id: str) -> str:
    return f"er:patient:{patient_id}"


def _bed_location(bed_id: str) -> str:
    """Display location for a bed id used on equipment/nurse records (`bed3` -> `bed-3`)."""
    return f"bed-{bed_id.removeprefix('bed')}"


def init_state(store: StorageInterface) -> None:
    """Seed the equipment inventory."""
    for unit in EQUIPMENT:
        store.set(equipment_key(unit["id"]), dict(unit))


def is_low_supply(unit: dict) -> bool:
    """True for a consumable whose supply has fallen below the low threshold."""
    level = unit.get("supply_level")
    return level is not None and level < LOW_SUPPLY_THRESHOLD


def is_available(unit: dict) -> bool:
    """Availability is type-dependent: consumables must be free *and* above threshold; devices free."""
    if unit.get("in_use_by") is not None:
        return False
    if unit.get("supply_level") is not None:
        return not is_low_supply(unit)
    return True


def oxygen_unit_at_bed(store: StorageInterface, bed_id: str) -> str | None:
    """Return the oxygen equipment id attached to a bed, or None (first oxygen unit in its list)."""
    for eid in store.get(bed_key(bed_id)).get("equipment", []):
        if store.get(equipment_key(eid)).get("type") == "oxygen":
            return eid
    return None


def bed_for_equipment(store: StorageInterface, equipment_id: str) -> str | None:
    """Return the bed whose equipment list contains this unit, or None."""
    for bid in store.list_ids("bed"):
        if equipment_id in store.get(bed_key(bid)).get("equipment", []):
            return bid
    return None


def simulate_oxygen_drop(
    store: StorageInterface,
    bed_id: str,
    equipment_id: str | None = None,
    new_supply_level: int = 45,
    patient_spo2: int = 88,
) -> str | None:
    """Lower a bed's oxygen unit below threshold and the bed patient's spo2 (the scripted trigger).

    @spec OXY-FLOW-007 — drops the unit's `supply_level` (default 45, below the 50 threshold) and the
    occupant's `spo2` so the unit's agent then has cause to emit `LowSupplyAlert`. Returns the unit id,
    or None if the bed has no oxygen unit.
    """
    eid = equipment_id or oxygen_unit_at_bed(store, bed_id)
    if eid is None:
        return None
    store.update(equipment_key(eid), {"supply_level": new_supply_level})
    occupant = store.get(bed_key(bed_id)).get("occupied_by")
    if occupant:
        vitals = dict(store.get(patient_key(occupant)).get("vitals", {}))
        vitals["spo2"] = patient_spo2
        store.update(patient_key(occupant), {"vitals": vitals})
    return eid


def locate_replacement(
    store: StorageInterface, equip_type: str, exclude_id: str | None = None
) -> str | None:
    """Select a replacement unit of the same type, or None (decision R2-E).

    @spec OXY-FLOW-002 @spec OXY-FLOW-003 — any available same-type unit at/above the low threshold,
    sorted highest `supply_level` first then id ascending.
    @spec OXY-ERR-001 — never selects a busy unit or one whose own supply is below threshold.
    """
    candidates: list[tuple[int, str]] = []
    for eid in store.list_ids("equipment"):
        if eid == exclude_id:
            continue
        unit = store.get(equipment_key(eid))
        if unit.get("type") != equip_type or unit.get("in_use_by") is not None:
            continue
        level = unit.get("supply_level")
        if level is None or level < LOW_SUPPLY_THRESHOLD:
            continue
        candidates.append((level, eid))
    if not candidates:
        return None
    candidates.sort(key=lambda c: (-c[0], c[1]))
    return candidates[0][1]


def swap_oxygen_unit(
    store: StorageInterface, depleted_id: str, replacement_id: str, bed_id: str
) -> str | None:
    """Apply the oxygen swap to equipment, bed, and patient state (decision R2-C).

    @spec OXY-FLOW-005 — replacement → in use at the bed; depleted → freed + `needs_restock`; the bed's
    equipment list updated; the occupant's spo2 restored to 96. (The nurse move lives in `nurse.py`.)
    Idempotent: a duplicate/late dispatch response that re-applies the same swap writes nothing new.
    Returns the patient id on the bed, or None.
    """
    occupant = store.get(bed_key(bed_id)).get("occupied_by")
    bed = store.get(bed_key(bed_id))
    if bed.get("equipment") == [replacement_id] and store.get(
        equipment_key(replacement_id)
    ).get("in_use_by") == occupant:
        return occupant  # swap already applied — no-op
    loc = _bed_location(bed_id)
    store.update(equipment_key(replacement_id), {"in_use_by": occupant, "location": loc})
    store.update(
        equipment_key(depleted_id),
        {"in_use_by": None, "location": "storage", "needs_restock": True},
    )
    store.update(bed_key(bed_id), {"equipment": [replacement_id]})
    if occupant:
        vitals = dict(store.get(patient_key(occupant)).get("vitals", {}))
        vitals["spo2"] = 96
        store.update(patient_key(occupant), {"vitals": vitals})
    return occupant


def build_agents(store: StorageInterface) -> list[Agent]:
    """Create one EquipmentAgent per unit, each wired with the Event-2 oxygen handlers."""
    agents: list[Agent] = []
    for unit in EQUIPMENT:
        eid = unit["id"]
        agent = Agent(name=f"er-{eid}", seed=seed_for(eid), network="testnet")
        agent.on_message(SimulateOxygenDropRequest)(_make_simulate_handler(store, eid))
        agent.on_message(EquipmentLocateRequest)(_make_locate_handler(store, eid))
        agents.append(agent)
    return agents


def _make_simulate_handler(store: StorageInterface, equipment_id: str):
    async def on_simulate(ctx: Context, sender: str, msg: SimulateOxygenDropRequest):
        # @spec OXY-FLOW-007 — drop my own supply + the bed patient's spo2...
        simulate_oxygen_drop(
            store, msg.bed_id, equipment_id=equipment_id,
            new_supply_level=msg.new_supply_level, patient_spo2=msg.patient_spo2,
        )
        unit = store.get(equipment_key(equipment_id))
        ctx.logger.info(
            f"{equipment_id} supply dropped to {unit.get('supply_level')} — emitting LowSupplyAlert"
        )
        # @spec OXY-FLOW-001 — ...then autonomously push the alert to the Orchestrator, echoing the
        # flow_id so the Orchestrator can correlate this hop to the originating command (LLD §6).
        await ctx.send(
            ORCHESTRATOR_ADDRESS,
            LowSupplyAlert(
                equipment_id=equipment_id,
                type=unit.get("type", "oxygen"),
                supply_level=unit.get("supply_level", 0),
                location=unit.get("location", msg.bed_id),
                flow_id=msg.flow_id or None,
            ),
        )

    return on_simulate


def _make_locate_handler(store: StorageInterface, equipment_id: str):
    async def on_locate(ctx: Context, sender: str, msg: EquipmentLocateRequest):
        # @spec OXY-FLOW-003 — answer for myself: a same-type unit that is free and above threshold.
        unit = store.get(equipment_key(equipment_id))
        available = unit.get("type") == msg.type and is_available(unit)
        await ctx.send(
            sender,
            EquipmentLocateResponse(
                equipment_id=equipment_id if available else None,
                location=unit.get("location", ""),
                available=available,
                flow_id=msg.flow_id,
            ),
        )

    return on_locate
