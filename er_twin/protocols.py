"""Shared message vocabulary for the whole ER twin (LLD section 3).

All inter-agent messages are uAgent `Model` subclasses, named as request/response pairs. This is
the single source of truth every agent imports — do not redefine these elsewhere.
"""

from uagents import Model

# --- Event 1: Patient Intake ---


class PatientIntakeRequest(Model):
    name: str
    chief_complaint: str
    vitals: dict


class PatientIntakeResponse(Model):
    patient_id: str
    record: dict


class PatientBindRequest(Model):
    patient_id: str
    record: dict


class PatientBindResponse(Model):
    patient_id: str
    agent_id: str
    bound: bool


class TriageRequest(Model):
    patient_id: str
    chief_complaint: str
    vitals: dict


class TriageResponse(Model):
    patient_id: str
    acuity: int
    specialty: str = "general"  # set by Triage; drives bed specialty + doctor paging (decision Gap 1)


class BedAssignRequest(Model):
    patient_id: str
    required_specialty: str


class BedAssignResponse(Model):
    patient_id: str
    bed_id: str | None = None
    success: bool


class StaffAssignRequest(Model):
    patient_id: str
    bed_id: str


class StaffAssignResponse(Model):
    patient_id: str
    staff_id: str
    accepted: bool


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


# --- Event 3: Status Summary ---


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
