"""Per-flow correlation state for discharge and resolve flows.

DischargeFlow tracks a single confirm-discharge command while it awaits the PatientDischargeResponse
from the bound PatientAgent.

ResolveFlow tracks a single resolve command while it drains a queue of release requests to the bed,
nurse, and doctor agents.  Each hop sends one request; the response handler pops the completed item
and sends the next, until the queue is empty.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DischargeFlow:
    """Per-flow state for a discharge-confirm command (keyed by flow_id in orchestrator.discharge_flows)."""

    flow_id: str
    session_id: str
    chat_sender: str
    patient_id: str
    mrn: str
    name: str
    bed_id: str | None
    nurse_id: str | None
    doctor_id: str | None
    active_event_id: str = ""
    lines: list[dict] = field(default_factory=list)


@dataclass
class ResolveFlow:
    """Per-flow state for a resolve command (keyed by flow_id in orchestrator.resolve_flows).

    release_queue is a list of dicts with keys:
      {"kind": "bed"|"nurse"|"doctor", "id": "<bed_id or staff_id>", "patient_id": "<patient_id>"}
    Items are processed one at a time (pop index 0, send, wait for response, repeat).
    """

    flow_id: str
    session_id: str
    chat_sender: str
    event_id: str
    event_type: str
    patient_id: str | None
    release_queue: list[dict] = field(default_factory=list)
