"""Event registry — maps intent keys to handler instances."""

from __future__ import annotations

from er_twin.events.base import EventHandler
from er_twin.events.discharge import DischargeHandler
from er_twin.events.intake import IntakeHandler
from er_twin.events.oxygen import OxygenHandler
from er_twin.events.ping import PingHandler
from er_twin.events.resolve import ResolveHandler
from er_twin.events.summary import SummaryHandler

EVENT_REGISTRY: dict[str, EventHandler] = {
    "intake": IntakeHandler(),
    "oxygen": OxygenHandler(),
    "summary": SummaryHandler(),
    "discharge": DischargeHandler(),
    "resolve": ResolveHandler(),
    "ping": PingHandler(),
}


def all_keywords() -> dict[str, tuple[str, ...]]:
    return {k: h.keywords for k, h in EVENT_REGISTRY.items()}


def mock_replies() -> dict[str, str]:
    return {k: h.mock_reply for k, h in EVENT_REGISTRY.items() if h.mock_reply}


def incident_types() -> dict[str, str]:
    return {k: h.incident_type for k, h in EVENT_REGISTRY.items() if h.incident_type}


def visual_styles() -> dict[str, str]:
    styles: dict[str, str] = {}
    for h in EVENT_REGISTRY.values():
        if h.incident_type and h.visual_style:
            styles[h.incident_type] = h.visual_style
    return styles
