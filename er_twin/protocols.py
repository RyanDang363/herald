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


class LowSupplyAlert(Model):
    equipment_id: str
    type: str
    supply_level: int
    location: str


class EquipmentLocateRequest(Model):
    type: str
    near_location: str


class EquipmentLocateResponse(Model):
    equipment_id: str | None = None
    location: str
    available: bool


class StaffDispatchRequest(Model):
    task: str
    target_location: str
    equipment_id: str


class StaffDispatchResponse(Model):
    staff_id: str
    accepted: bool
    eta_note: str


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
