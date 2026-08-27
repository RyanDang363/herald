"""Shared message vocabulary for the whole ER twin (LLD section 3).

All inter-agent messages are uAgent `Model` subclasses, named as request/response pairs. This is
the single source of truth every agent imports — do not redefine these elsewhere.

Intake-related messages carry a `flow_id` so that the Orchestrator's response handlers can correlate
replies back to the originating intake flow across async hops (same pattern as the oxygen flow).
"""

from uagents import Model

# --- Event 1: Patient Intake ---
#
# The intake flow is a sequential multi-hop: Orchestrator → Admissions → Patient → Triage → Bed →
# Nurse → Doctor (optional). Each hop carries `flow_id` so the Orchestrator's `@on_message` handlers
# can advance the correct IntakeFlow state machine (INTAKE-FLOW-* spec).


class PatientIntakeRequest(Model):
    name: str
    chief_complaint: str
    vitals: dict
    mrn: str = ""
    flow_id: str = ""


class PatientIntakeResponse(Model):
    patient_id: str
    record: dict
    created: bool
    flow_id: str = ""


class PatientBindRequest(Model):
    patient_id: str
    record: dict
    flow_id: str = ""


class PatientBindResponse(Model):
    patient_id: str
    agent_id: str
    bound: bool
    flow_id: str = ""


class TriageRequest(Model):
    patient_id: str
    chief_complaint: str
    vitals: dict
    flow_id: str = ""


class TriageResponse(Model):
    patient_id: str
    acuity: int
    specialty: str = "general"
    flow_id: str = ""


class BedAssignRequest(Model):
    patient_id: str
    required_specialty: str
    preferred_bed_id: str | None = None  # admin override from the proposal card
    flow_id: str = ""


class BedAssignResponse(Model):
    patient_id: str
    bed_id: str | None = None
    success: bool
    flow_id: str = ""


class StaffAssignRequest(Model):
    patient_id: str
    bed_id: str
    # "nurse" or "doctor" — echoed back in the response so the handler knows which step completed.
    role: str = "nurse"
    flow_id: str = ""


class StaffAssignResponse(Model):
    patient_id: str
    staff_id: str
    accepted: bool
    role: str = "nurse"
    flow_id: str = ""


# --- Event 2: Low Oxygen Alert ---
#
# Every oxygen-flow message carries a `flow_id` correlation token. The Orchestrator keys the in-progress
# flow context (bed, units, nurse, chat session) by it so the multi-hop async flow (alert → locate →
# dispatch) survives overlapping/autonomous alerts and treats late/duplicate responses as no-ops
# (LLD §6). The unit's agent echoes the `flow_id` it received into its responses; an autonomous alert
# leaves `flow_id` null and the Orchestrator mints one.


class LowSupplyAlert(Model):
    equipment_id: str
    type: str
    supply_level: int
    location: str
    flow_id: str | None = None  # null for an autonomous alert (no simulate trigger)


class EquipmentLocateRequest(Model):
    type: str
    near_location: str
    flow_id: str = ""


class EquipmentLocateResponse(Model):
    location: str
    available: bool
    equipment_id: str | None = None
    flow_id: str = ""


class StaffDispatchRequest(Model):
    task: str
    target_location: str
    equipment_id: str
    flow_id: str = ""


class StaffDispatchResponse(Model):
    staff_id: str
    accepted: bool
    eta_note: str
    flow_id: str = ""


# Internal demo trigger (decision Gap 4): the scripted chat command makes the EquipmentAgent at the
# named bed drop below threshold, so the agent itself emits the autonomous `LowSupplyAlert`.
class SimulateOxygenDropRequest(Model):
    bed_id: str
    equipment_id: str | None = None  # default: the oxygen unit attached to bed_id
    patient_spo2: int = 88
    new_supply_level: int = 45  # below the low-supply threshold (50)
    flow_id: str = ""


# DEFERRED / UNUSED (decision Gap 4): the EquipmentAgent answers a SimulateOxygenDropRequest by
# autonomously emitting `LowSupplyAlert`, not a response — there is no producer or consumer of this
# model. Retained as historical contract intent; do not wire without a handler + test (LLD §3).
class SimulateOxygenDropResponse(Model):
    bed_id: str
    equipment_id: str
    triggered: bool


# --- Event 3: Patient Discharge ---
#
# The discharge flow is sequential: Orchestrator → PatientAgent (mark discharged + record sign-off).
# Resource release (bed, staff) runs as a separate resolve flow when the operator calls "resolve".


class PatientDischargeRequest(Model):
    patient_id: str
    nurse_id: str | None = None
    doctor_id: str | None = None
    flow_id: str = ""


class PatientDischargeResponse(Model):
    patient_id: str
    confirmed: bool
    confirmation: str = ""
    flow_id: str = ""


# --- Event 4: Resolve / resource release ---
#
# The resolve flow drains a release queue sequentially: bed → nurses → doctors. Each hop sends one
# release request to the owning agent and waits for its response before sending the next.


class BedReleaseRequest(Model):
    bed_id: str
    patient_id: str
    flow_id: str = ""


class BedReleaseResponse(Model):
    bed_id: str
    released: bool
    flow_id: str = ""


class StaffReleaseRequest(Model):
    patient_id: str
    staff_id: str
    role: str = "nurse"  # "nurse" or "doctor"
    flow_id: str = ""


class StaffReleaseResponse(Model):
    patient_id: str
    staff_id: str
    role: str = "nurse"
    released: bool
    flow_id: str = ""


# --- Event 5: Status Summary ---


class StateQueryRequest(Model):
    entity_type: str


class StateQueryResponse(Model):
    entity_type: str
    entities: list


# --- First-slice skeleton ---


class PingRequest(Model):
    text: str


class PingResponse(Model):
    text: str
    agent_id: str
