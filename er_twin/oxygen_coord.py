"""Low-oxygen coordination pure functions (OXY-*)."""

from __future__ import annotations

import re

from er_twin.agents import equipment, nurse
from er_twin.display import display
from er_twin.storage import StorageInterface


def should_start_o2_dispatch(in_flight: dict[str, str], equipment_id: str) -> bool:
    return equipment_id not in in_flight


def apply_oxygen_swap(
    store: StorageInterface, depleted_id: str, replacement_id: str, bed_id: str, nurse_id: str
) -> str | None:
    occupant = equipment.swap_oxygen_unit(store, depleted_id, replacement_id, bed_id)
    nurse.dispatch_nurse(store, nurse_id, bed_id)
    return occupant


def format_oxygen_confirmation(bed_id: str, replacement_id: str, nurse_id: str) -> str:
    return (
        f"Low O2 on {display(bed_id)} resolved: dispatched {display(nurse_id)} with "
        f"{display(replacement_id)}; patient SpO2 restored to 96%."
    )


def bed_from_text(text: str) -> str:
    match = re.search(r"bed\s*(\d+)", text.lower())
    return f"bed{match.group(1)}" if match else "bed3"


def cleanup_oxygen(
    flow_id: str,
    flows: dict,
    in_flight: dict,
    senders,
) -> None:
    flow = flows.pop(flow_id, None)
    if flow is not None:
        in_flight.pop(flow.alert_equipment_id, None)
        if flow.session_id:
            senders.forget(flow.session_id)
