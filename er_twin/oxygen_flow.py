"""Oxygen flow correlation state (LLD §6)."""

from dataclasses import dataclass, field


@dataclass
class OxygenFlow:
    """Per-flow context for the multi-hop oxygen event, keyed by `flow_id`."""

    flow_id: str
    bed_id: str
    alert_equipment_id: str
    session_id: str | None = None
    chat_sender: str | None = None
    replacement_id: str | None = None
    nurse_id: str | None = None
    status: str = "started"
    lines: list[dict] = field(default_factory=list)
