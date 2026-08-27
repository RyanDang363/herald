"""Intake flow correlation state (mirrors oxygen_flow.py for the multi-hop intake sequence).

Each `ctx.send` hop in the intake pipeline (Admissions → PatientBind → Triage → Bed → Nurse →
Doctor) echoes the originating `flow_id`. The Orchestrator's `@on_message` handlers look up the
corresponding `IntakeFlow` and advance it, keeping all mutable state here rather than in globals.
"""

from dataclasses import dataclass, field


@dataclass
class IntakeFlow:
    """Per-flow context for the multi-hop intake event, keyed by `flow_id`."""

    flow_id: str
    chat_sender: str
    session_id: str
    name: str
    chief_complaint: str
    vitals: dict
    mrn: str
    # Admin-selected resources (from the proposal card or chat override)
    preferred_bed_id: str | None = None
    preferred_nurse_id: str | None = None
    preferred_doctor_id: str | None = None
    # Active-events tracking (proposal card → confirmed event)
    active_event_id: str = ""
    # Accumulated state from successive hops
    patient_id: str | None = None
    acuity: int | None = None
    specialty: str = "general"
    bed_id: str | None = None
    nurse_id: str | None = None
    doctor_id: str | None = None
    error: str | None = None
    # Replay milestone lines accumulated across hops
    lines: list[dict] = field(default_factory=list)
