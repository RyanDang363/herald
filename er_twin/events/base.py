"""Event handler base types and shared dispatch context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from uagents import Context

from er_twin.memory import MemoryInterface
from er_twin.storage import StorageInterface

if TYPE_CHECKING:
    from er_twin.replay import ReplayRecorder


@dataclass
class PendingCommand:
    sender: str
    session_id: str
    text: str
    flow_id: str


@dataclass
class PendingProposal:
    """Multi-turn chat state kept open until the admin confirms or supplies missing fields."""

    kind: str  # awaiting_mrn | awaiting_complaint | intake_confirm | discharge_confirm
    event_type: str  # intake | discharge
    sender: str
    session_id: str
    mrn: str = ""
    name: str = ""
    chief_complaint: str = ""
    vitals: dict = field(default_factory=dict)
    patient_id: str = ""
    acuity: int | None = None
    specialty: str = ""
    proposed: dict = field(default_factory=dict)  # bed_id, nurse_id, doctor_id
    lines: list[dict] = field(default_factory=list)
    active_event_id: str = ""  # pending_approval active event id (set in _propose)


@dataclass
class DispatchContext:
    """Shared orchestrator state passed into every event handler."""

    ctx: Context
    cmd: PendingCommand
    store: StorageInterface | None
    replay: ReplayRecorder
    memory: MemoryInterface
    session_pending: dict[str, PendingProposal]
    oxygen_flows: dict[str, Any]
    in_flight_o2_dispatches: dict[str, str]
    session_senders: Any
    pending_ping_sessions: list[tuple[str, str]]
    send_chat: Callable[..., Any]
    log_milestone: Callable[..., dict | None]
    record_milestone: Callable[..., dict | None]
    emit_replay: Callable[..., str | None]
    record_memory: Callable[..., None]
    recall_memory: Callable[[str], list[str]]
    new_flow_id: Callable[[str], str]
    complete_command: Callable[..., Any]


class EventHandler(ABC):
    """One subclass per ER event. Registered by key in EVENT_REGISTRY."""

    key: str
    keywords: tuple[str, ...] = ()
    mock_reply: str = ""
    incident_type: str = ""
    visual_style: str = ""
    logs_to_replay: bool = True  # summary sets False

    @abstractmethod
    async def dispatch(self, dctx: DispatchContext) -> bool:
        """Return True if synchronous (gate frees now), False if async."""

    async def resume(self, dctx: DispatchContext, pending: PendingProposal) -> bool:
        """Handle a follow-up message for an open session proposal."""
        return True
