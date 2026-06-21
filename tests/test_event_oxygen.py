"""Phase 4 — Event 2: Low Oxygen Alert (OXY-*).

The running Bureau realizes this event as **real async uAgent messaging** (the mandatory Fetch.ai
"agents messaging agents" showcase — decision 2026-06-20-intake-orchestration-mode): the EquipmentAgent
autonomously emits `LowSupplyAlert`, and the Orchestrator handles alert → locate → dispatch → swap in
separate `@on_message` handlers. The message handlers are thin wrappers over the pure domain functions
exercised here against an `InMemoryStore` (no live Bureau — flaky on Windows). Each test traces to an
EARS spec id.

Tests use the CLEAN seed (entity `init_state`, no `seed_baseline`) plus a minimal oxygen scenario
(p2 on bed3 with oxygen unit o2_1, nurse1 busy so nurse2 is the deterministic dispatch pick).
"""

from er_twin.agents import bed, doctor, equipment, nurse, orchestrator, patient
from er_twin.storage import InMemoryStore


def _oxygen_store() -> InMemoryStore:
    """Clean seed + a minimal mid-event oxygen scenario (mirrors the demo baseline, minimally)."""
    store = InMemoryStore()
    for module in (patient, bed, nurse, doctor, equipment):
        module.init_state(store)
    # p2 on bed-3 breathing off oxygen unit o2_1 (pre-drop supply above threshold).
    store.set("er:patient:p2", {
        "id": "p2", "name": "Avery Chen", "chief_complaint": "shortness of breath",
        "acuity": 3, "specialty": "general", "status": "in_treatment",
        "vitals": {"spo2": 92, "heart_rate": 104}, "assigned_bed": "bed3", "care_team": ["doc2"],
    })
    store.update("er:bed:bed3", {"occupied_by": "p2", "status": "occupied", "equipment": ["o2_1"]})
    store.update("er:equipment:o2_1", {"supply_level": 55, "in_use_by": "p2", "location": "bed-3"})
    store.update("er:nurse:nurse1", {"available": False, "location": "bed-3", "assignments": ["p2"]})
    return store


# --- Equipment lookups: bed <-> oxygen unit (used by the chat trigger + autonomous alert) ---


def test_oxygen_unit_lookup_helpers():
    store = _oxygen_store()
    assert equipment.oxygen_unit_at_bed(store, "bed3") == "o2_1"
    assert equipment.bed_for_equipment(store, "o2_1") == "bed3"
    assert equipment.oxygen_unit_at_bed(store, "bed1") is None  # no oxygen attached


# --- OXY-FLOW-007: the EquipmentAgent drops its own supply + the bed patient's spo2 ---


def test_simulate_oxygen_drop_lowers_supply_and_spo2():
    # @spec OXY-FLOW-007
    store = _oxygen_store()
    eid = equipment.simulate_oxygen_drop(store, "bed3")
    assert eid == "o2_1"
    assert store.get("er:equipment:o2_1")["supply_level"] == 45
    # @spec OXY-FLOW-001 — now below the low threshold, the alert condition holds.
    assert equipment.is_low_supply(store.get("er:equipment:o2_1")) is True
    assert store.get("er:patient:p2")["vitals"]["spo2"] == 88


# --- OXY-FLOW-002/003 + R2-E: locate a replacement (highest supply >= threshold, then id) ---


def test_locate_replacement_picks_same_type_above_threshold():
    # @spec OXY-FLOW-002
    # @spec OXY-FLOW-003
    store = _oxygen_store()
    equipment.simulate_oxygen_drop(store, "bed3")
    assert equipment.locate_replacement(store, "oxygen", exclude_id="o2_1") == "o2_2"


def test_locate_replacement_sorts_highest_supply_then_id():
    # @spec OXY-FLOW-002 — R2-E deterministic sort.
    store = _oxygen_store()
    store.set("er:equipment:o2_3", {
        "id": "o2_3", "type": "oxygen", "supply_level": 88, "in_use_by": None, "location": "storage",
    })
    store.update("er:equipment:o2_2", {"supply_level": 88})  # tie with o2_3 -> id ascending wins
    assert equipment.locate_replacement(store, "oxygen", exclude_id="o2_1") == "o2_2"
    store.update("er:equipment:o2_3", {"supply_level": 95})  # now o2_3 has the most supply
    assert equipment.locate_replacement(store, "oxygen", exclude_id="o2_1") == "o2_3"


def test_locate_replacement_none_when_no_unit_qualifies():
    # @spec OXY-ERR-001 — never returns a sub-threshold or busy unit; None when none qualify.
    store = _oxygen_store()
    equipment.simulate_oxygen_drop(store, "bed3")
    store.update("er:equipment:o2_2", {"supply_level": 40})  # below threshold
    assert equipment.locate_replacement(store, "oxygen", exclude_id="o2_1") is None
    store.update("er:equipment:o2_2", {"supply_level": 49, "in_use_by": None})  # free but still low
    assert equipment.locate_replacement(store, "oxygen", exclude_id="o2_1") is None


# --- OXY-FLOW-005 / R2-C: the swap mutates equipment, bed, patient, and nurse ---


def test_oxygen_swap_applies_all_mutations():
    # @spec OXY-FLOW-005
    store = _oxygen_store()
    equipment.simulate_oxygen_drop(store, "bed3")
    occupant = orchestrator.apply_oxygen_swap(store, "o2_1", "o2_2", "bed3", "nurse2")
    assert occupant == "p2"

    o2_2 = store.get("er:equipment:o2_2")
    o2_1 = store.get("er:equipment:o2_1")
    assert o2_2["in_use_by"] == "p2" and o2_2["location"] == "bed-3"
    assert o2_1["in_use_by"] is None and o2_1["location"] == "storage"
    assert o2_1["needs_restock"] is True
    assert store.get("er:bed:bed3")["equipment"] == ["o2_2"]
    assert store.get("er:patient:p2")["vitals"]["spo2"] == 96  # restored

    n2 = store.get("er:nurse:nurse2")
    assert n2["available"] is False and n2["location"] == "bed3"
    assert "oxygen_dispatch:bed3" in n2["assignments"]


def test_dispatch_nurse_is_idempotent():
    # @spec OXY-FLOW-005 — re-dispatch of the same nurse to the same bed writes nothing new.
    store = _oxygen_store()
    assert nurse.dispatch_nurse(store, "nurse2", "bed3") is True
    assert nurse.dispatch_nurse(store, "nurse2", "bed3") is True
    assert store.get("er:nurse:nurse2")["assignments"].count("oxygen_dispatch:bed3") == 1


# --- Full flow, composed in OXY order (what the async handlers drive across hops) ---


def test_full_oxygen_flow_end_to_end():
    # @spec OXY-FLOW-001
    # @spec OXY-FLOW-002
    # @spec OXY-FLOW-003
    # @spec OXY-FLOW-004
    # @spec OXY-FLOW-005
    # @spec OXY-FLOW-006
    # @spec OXY-FLOW-007
    store = _oxygen_store()

    # OXY-FLOW-007 — drop simulated at bed-3.
    eid = equipment.simulate_oxygen_drop(store, "bed3")
    assert eid == "o2_1" and equipment.is_low_supply(store.get("er:equipment:o2_1"))

    # OXY-FLOW-002/003 — locate replacement -> o2_2.
    replacement = equipment.locate_replacement(store, "oxygen", exclude_id=eid)
    assert replacement == "o2_2"

    # OXY-FLOW-004 — dispatch nurse; nurse1 busy so nurse2 is the deterministic pick.
    nurse_id = nurse.find_available_nurse(store)
    assert nurse_id == "nurse2"

    # OXY-FLOW-005 — apply swap.
    occupant = orchestrator.apply_oxygen_swap(store, eid, replacement, "bed3", nurse_id)
    assert occupant == "p2"
    assert store.get("er:patient:p2")["vitals"]["spo2"] == 96
    assert store.get("er:bed:bed3")["equipment"] == ["o2_2"]

    # OXY-FLOW-006 — chat confirmation names unit, nurse, and bed.
    msg = orchestrator.format_oxygen_confirmation("bed3", replacement, nurse_id)
    assert "bed-3" in msg
    assert "o2-2" in msg
    assert "Nurse Chen" in msg


# --- OXY-IDEM-001: in-flight dispatch dedupe ---


def test_in_flight_dispatch_dedupe():
    # @spec OXY-IDEM-001
    in_flight: dict[str, str] = {}
    assert orchestrator.should_start_o2_dispatch(in_flight, "o2_1") is True
    in_flight["o2_1"] = "oxygen-1"  # dispatch started (value is now the flow_id)
    assert orchestrator.should_start_o2_dispatch(in_flight, "o2_1") is False  # duplicate ignored
    assert orchestrator.should_start_o2_dispatch(in_flight, "o2_2") is True  # a different unit is fine


def test_oxygen_swap_is_idempotent():
    # @spec OXY-FLOW-005 — a duplicate/late StaffDispatchResponse must not double-apply the swap.
    store = _oxygen_store()
    equipment.simulate_oxygen_drop(store, "bed3")
    occ1 = orchestrator.apply_oxygen_swap(store, "o2_1", "o2_2", "bed3", "nurse2")
    snapshot = (
        store.get("er:equipment:o2_2"), store.get("er:equipment:o2_1"),
        store.get("er:bed:bed3"), store.get("er:nurse:nurse2"),
    )
    occ2 = orchestrator.apply_oxygen_swap(store, "o2_1", "o2_2", "bed3", "nurse2")  # re-apply
    assert occ1 == occ2 == "p2"
    assert (
        store.get("er:equipment:o2_2"), store.get("er:equipment:o2_1"),
        store.get("er:bed:bed3"), store.get("er:nurse:nurse2"),
    ) == snapshot  # no second mutation
