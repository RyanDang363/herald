"""In-process intake flow tests using a fake uAgent Context.

The fake Context captures every `ctx.send(address, message)` call and routes it to the correct
agent handler based on address → handler mapping. This lets the full multi-hop intake pipeline
(Orchestrator → Admissions → PatientBind → Triage → Bed → Nurse → Doctor) be exercised without
a live Bureau.

Each test traces back to INTAKE-FLOW-* EARS specs.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from er_twin.addresses import (
    ADMISSIONS_ADDRESS,
    TRIAGE_ADDRESS,
    bed_address,
    doctor_address,
    nurse_address,
)
from er_twin.agents import admissions, bed, doctor, nurse, patient, triage
from er_twin.agents.orchestrator import (
    _on_bed_response,
    _on_bind_response,
    _on_intake_response,
    _on_staff_response,
    _on_triage_response,
    _start_intake_flow,
    intake_flows,
    set_store,
)
from er_twin.intake_flow import IntakeFlow
from er_twin.protocols import (
    BedAssignRequest,
    BedAssignResponse,
    PatientBindRequest,
    PatientBindResponse,
    PatientIntakeRequest,
    PatientIntakeResponse,
    StaffAssignRequest,
    StaffAssignResponse,
    TriageRequest,
    TriageResponse,
)
from er_twin.storage import InMemoryStore


# ---------------------------------------------------------------------------
# Fake Context
# ---------------------------------------------------------------------------


class FakeContext:
    """Minimal fake uAgent Context that captures sent messages and supports routing.

    Usage:
        ctx = FakeContext(router)
        await ctx.send(address, message)

    where `router` is a dict: address → async handler(ctx, sender, message).
    Unrouted sends are recorded in `ctx.unrouted`.
    """

    def __init__(self, router: dict[str, Any] | None = None) -> None:
        self._router = router or {}
        self.sent: list[tuple[str, Any]] = []  # [(address, message), ...]
        self.unrouted: list[tuple[str, Any]] = []
        self.logger = MagicMock()
        self.session = "fake-session-0001"

    async def send(self, address: str, message: Any) -> None:
        self.sent.append((address, message))
        handler = self._router.get(address)
        if handler is not None:
            await handler(self, "orchestrator-address", message)
        else:
            self.unrouted.append((address, message))


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_intake_flows():
    """Clear the global intake_flows dict before and after each test."""
    intake_flows.clear()
    yield
    intake_flows.clear()


@pytest.fixture()
def store() -> InMemoryStore:
    s = InMemoryStore()
    admissions.init_state(s) if hasattr(admissions, "init_state") else None
    patient.init_state(s)
    triage.init_state(s) if hasattr(triage, "init_state") else None
    bed.init_state(s)
    nurse.init_state(s)
    doctor.init_state(s)
    set_store(s)
    return s


def _flow(store, **overrides) -> IntakeFlow:
    defaults: dict = dict(
        flow_id="chat-1",
        chat_sender="user-addr",
        session_id="sess-001",
        name="Jordan Lee",
        chief_complaint="chest pain",
        vitals={"spo2": 96, "heart_rate": 112},
        mrn="MRN-0005",
    )
    defaults.update(overrides)
    return IntakeFlow(**defaults)


# ---------------------------------------------------------------------------
# Unit tests: individual hop handlers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_intake_sends_to_admissions(store):
    """_start_intake_flow sends PatientIntakeRequest to ADMISSIONS_ADDRESS. @spec INTAKE-FLOW-001"""
    ctx = FakeContext()
    flow = _flow(store)
    await _start_intake_flow(ctx, flow)

    assert flow.flow_id in intake_flows
    assert len(ctx.sent) == 1
    addr, msg = ctx.sent[0]
    assert addr == ADMISSIONS_ADDRESS
    assert isinstance(msg, PatientIntakeRequest)
    assert msg.flow_id == "chat-1"
    assert msg.name == "Jordan Lee"


@pytest.mark.asyncio
async def test_intake_response_new_patient_binds_slot(store):
    """PatientIntakeResponse(created=True) → sends PatientBindRequest. @spec INTAKE-FLOW-002"""
    ctx = FakeContext()
    flow = _flow(store)
    intake_flows["chat-1"] = flow

    patient_id, record, _ = admissions.intake(
        store, "Jordan Lee", "chest pain", {"spo2": 96}, "MRN-0005"
    )
    msg = PatientIntakeResponse(
        patient_id=patient_id, record=record, created=True, flow_id="chat-1"
    )
    await _on_intake_response(ctx, msg)

    assert flow.patient_id == patient_id
    assert len(ctx.sent) == 1
    addr, req = ctx.sent[0]
    # should be sent to a patient-agent address
    assert addr.startswith("agent1") or "agent" in addr  # address format
    assert isinstance(req, PatientBindRequest)
    assert req.patient_id == patient_id


@pytest.mark.asyncio
async def test_intake_response_duplicate_short_circuits(store):
    """PatientIntakeResponse(created=False) → _finish_intake. @spec INTAKE-IDEM-001"""
    ctx = FakeContext()
    flow = _flow(store)
    intake_flows["chat-1"] = flow

    patient_id, record, _ = admissions.intake(
        store, "Jordan Lee", "chest pain", {"spo2": 96}, "MRN-0005"
    )
    msg = PatientIntakeResponse(
        patient_id=patient_id, record=record, created=False, flow_id="chat-1"
    )
    # _finish_intake tries to call _complete_command and _send_chat which need the gate;
    # mock those to isolate this unit test.
    from er_twin.agents import orchestrator as orch

    orch._complete_command = AsyncMock()
    orch._send_chat = AsyncMock()

    await _on_intake_response(ctx, msg)
    # Should not have sent any bind request
    assert not any(isinstance(m, PatientBindRequest) for _, m in ctx.sent)


@pytest.mark.asyncio
async def test_bind_response_advances_to_triage(store):
    """PatientBindResponse(bound=True) → sends TriageRequest. @spec INTAKE-BIND-002"""
    ctx = FakeContext()
    # Create and register the patient record so bind_slot can hydrate it
    patient_id, record, _ = admissions.intake(
        store, "Jordan Lee", "chest pain", {"spo2": 96}, "MRN-0005"
    )
    flow = _flow(store)
    flow.patient_id = patient_id
    intake_flows["chat-1"] = flow

    slot = patient.find_idle_slot(store)
    patient.bind_slot(store, slot, patient_id, record)

    msg = PatientBindResponse(patient_id=patient_id, agent_id="patient-1", bound=True, flow_id="chat-1")
    await _on_bind_response(ctx, msg)

    assert len(ctx.sent) == 1
    addr, req = ctx.sent[0]
    assert addr == TRIAGE_ADDRESS
    assert isinstance(req, TriageRequest)
    assert req.patient_id == patient_id
    assert req.flow_id == "chat-1"


@pytest.mark.asyncio
async def test_bind_response_pool_exhausted_stops(store):
    """PatientBindResponse(bound=False) → terminates flow. @spec INTAKE-BIND-003"""
    from er_twin.agents import orchestrator as orch

    orch._complete_command = AsyncMock()
    orch._send_chat = AsyncMock()

    ctx = FakeContext()
    patient_id, record, _ = admissions.intake(
        store, "Jordan Lee", "chest pain", {"spo2": 96}, "MRN-0005"
    )
    flow = _flow(store)
    flow.patient_id = patient_id
    intake_flows["chat-1"] = flow

    msg = PatientBindResponse(patient_id=patient_id, agent_id="patient-1", bound=False, flow_id="chat-1")
    await _on_bind_response(ctx, msg)

    assert flow.error == "patient_capacity_reached"
    orch._complete_command.assert_called_once()


@pytest.mark.asyncio
async def test_triage_response_advances_to_bed(store):
    """TriageResponse → sends BedAssignRequest. @spec INTAKE-FLOW-004"""
    ctx = FakeContext()
    patient_id, record, _ = admissions.intake(
        store, "Jordan Lee", "chest pain", {"spo2": 96}, "MRN-0005"
    )
    flow = _flow(store)
    flow.patient_id = patient_id
    intake_flows["chat-1"] = flow

    msg = TriageResponse(patient_id=patient_id, acuity=2, specialty="cardiology", flow_id="chat-1")
    await _on_triage_response(ctx, msg)

    assert flow.acuity == 2
    assert flow.specialty == "cardiology"
    assert len(ctx.sent) == 1
    addr, req = ctx.sent[0]
    assert isinstance(req, BedAssignRequest)
    assert addr == bed_address("bed1")  # bed1 is cardiology specialty


@pytest.mark.asyncio
async def test_triage_response_no_bed_stops(store):
    """TriageResponse when all beds occupied → terminates with no_bed_available. @spec INTAKE-ERR-002"""
    from er_twin.agents import orchestrator as orch

    orch._complete_command = AsyncMock()

    ctx = FakeContext()
    # Occupy all beds
    for bid in bed.BEDS:
        store.update(bed.bed_key(bid), {"occupied_by": "p-dummy", "status": "occupied"})

    patient_id, record, _ = admissions.intake(
        store, "Jordan Lee", "chest pain", {"spo2": 96}, "MRN-0005"
    )
    flow = _flow(store)
    flow.patient_id = patient_id
    intake_flows["chat-1"] = flow

    msg = TriageResponse(patient_id=patient_id, acuity=2, specialty="cardiology", flow_id="chat-1")
    await _on_triage_response(ctx, msg)

    assert flow.error == "no_bed_available"
    orch._complete_command.assert_called_once()


@pytest.mark.asyncio
async def test_bed_response_advances_to_nurse(store):
    """BedAssignResponse(success=True) → sends StaffAssignRequest(role='nurse'). @spec INTAKE-FLOW-007"""
    ctx = FakeContext()
    patient_id, record, _ = admissions.intake(
        store, "Jordan Lee", "chest pain", {"spo2": 96}, "MRN-0005"
    )
    flow = _flow(store)
    flow.patient_id = patient_id
    flow.acuity = 2
    flow.specialty = "cardiology"
    intake_flows["chat-1"] = flow

    msg = BedAssignResponse(patient_id=patient_id, bed_id="bed1", success=True, flow_id="chat-1")
    await _on_bed_response(ctx, msg)

    assert flow.bed_id == "bed1"
    assert len(ctx.sent) == 1
    addr, req = ctx.sent[0]
    assert isinstance(req, StaffAssignRequest)
    assert req.role == "nurse"
    assert addr == nurse_address("nurse1")


@pytest.mark.asyncio
async def test_nurse_response_pages_doctor_for_urgent(store):
    """StaffAssignResponse(role=nurse, acuity≤2) → sends StaffAssignRequest(role='doctor'). @spec INTAKE-FLOW-010"""
    ctx = FakeContext()
    patient_id, record, _ = admissions.intake(
        store, "Jordan Lee", "chest pain", {"spo2": 96}, "MRN-0005"
    )
    flow = _flow(store)
    flow.patient_id = patient_id
    flow.acuity = 2
    flow.specialty = "cardiology"
    flow.bed_id = "bed1"
    intake_flows["chat-1"] = flow

    msg = StaffAssignResponse(
        patient_id=patient_id, staff_id="nurse1", accepted=True, role="nurse", flow_id="chat-1"
    )
    await _on_staff_response(ctx, msg)

    assert flow.nurse_id == "nurse1"
    assert len(ctx.sent) == 1
    addr, req = ctx.sent[0]
    assert isinstance(req, StaffAssignRequest)
    assert req.role == "doctor"
    assert addr == doctor_address("doc1")  # cardiology specialty


@pytest.mark.asyncio
async def test_nurse_response_skips_doctor_for_low_acuity(store):
    """StaffAssignResponse(role=nurse, acuity>2) → finalizes without paging doctor. @spec INTAKE-FLOW-011"""
    from er_twin.agents import orchestrator as orch

    orch._complete_command = AsyncMock()

    ctx = FakeContext()
    patient_id, record, _ = admissions.intake(
        store, "Jordan Lee", "ankle injury", {"spo2": 98}, "MRN-0006"
    )
    flow = _flow(store, chief_complaint="ankle injury", mrn="MRN-0006")
    flow.patient_id = patient_id
    flow.acuity = 4  # non-urgent → no doctor
    flow.specialty = "general"
    flow.bed_id = "bed2"
    intake_flows["chat-1"] = flow

    msg = StaffAssignResponse(
        patient_id=patient_id, staff_id="nurse1", accepted=True, role="nurse", flow_id="chat-1"
    )
    await _on_staff_response(ctx, msg)

    # No doctor request sent
    assert not any(
        isinstance(m, StaffAssignRequest) and m.role == "doctor" for _, m in ctx.sent
    )
    orch._complete_command.assert_called_once()


@pytest.mark.asyncio
async def test_full_happy_path_hop_by_hop(store):
    """Full intake pipeline hop-by-hop: admissions → bind → triage → bed → nurse → doctor.

    Validates that each hop sends the right message to the right address and that the flow
    state accumulates correctly end-to-end. @spec INTAKE-FLOW-001 through INTAKE-FLOW-011
    """
    from er_twin.agents import orchestrator as orch

    orch._complete_command = AsyncMock()
    orch._send_chat = AsyncMock()

    # Build routing table: address → real handler (derived from agents with shared store)
    bed.build_agents(store)
    nurse.build_agents(store)
    doctor.build_agents(store)
    admissions.build_agents(store)
    triage.build_agents(store)
    patient.build_agents(store)

    # The router maps each agent's address to its registered handler.
    # Since on_message decorators run at module import (build_agents), we can call the handlers
    # directly by looking at the agent's message handlers.
    # For this integration test, we just drive the orchestrator functions directly.

    flow = _flow(store)
    ctx = FakeContext()

    # Hop 1: start → admissions
    await _start_intake_flow(ctx, flow)
    assert ctx.sent[-1][0] == ADMISSIONS_ADDRESS

    # Hop 2: admissions → bind
    patient_id, record, created = admissions.intake(
        store, flow.name, flow.chief_complaint, flow.vitals, flow.mrn
    )
    assert created
    ctx.sent.clear()
    await _on_intake_response(
        ctx,
        PatientIntakeResponse(
            patient_id=patient_id, record=record, created=True, flow_id="chat-1"
        ),
    )
    assert isinstance(ctx.sent[-1][1], PatientBindRequest)

    # Hop 3: bind → triage
    slot = patient.find_idle_slot(store)
    patient.bind_slot(store, slot, patient_id, store.get(patient.patient_key(patient_id)))
    ctx.sent.clear()
    await _on_bind_response(
        ctx,
        PatientBindResponse(
            patient_id=patient_id, agent_id=f"patient-{slot}", bound=True, flow_id="chat-1"
        ),
    )
    assert ctx.sent[-1][0] == TRIAGE_ADDRESS

    # Hop 4: triage → bed
    acuity, specialty = triage.assess("chest pain")
    ctx.sent.clear()
    await _on_triage_response(
        ctx,
        TriageResponse(patient_id=patient_id, acuity=acuity, specialty=specialty, flow_id="chat-1"),
    )
    bed_addr, bed_req = ctx.sent[-1]
    assert isinstance(bed_req, BedAssignRequest)

    # Hop 5: bed → nurse
    chosen_bed = bed.find_available_bed(store, specialty)
    assert chosen_bed is not None
    bed.assign_patient_to_bed(store, patient_id, chosen_bed)
    store.update(patient.patient_key(patient_id), {"status": "admitted"})
    ctx.sent.clear()
    await _on_bed_response(
        ctx,
        BedAssignResponse(
            patient_id=patient_id, bed_id=chosen_bed, success=True, flow_id="chat-1"
        ),
    )
    nurse_addr, nurse_req = ctx.sent[-1]
    assert isinstance(nurse_req, StaffAssignRequest) and nurse_req.role == "nurse"

    # Hop 6: nurse → doctor (acuity 2 → page doctor)
    chosen_nurse = nurse.find_available_nurse(store)
    assert chosen_nurse is not None
    nurse.assign_nurse(store, chosen_nurse, patient_id, bed_id=chosen_bed)
    ctx.sent.clear()
    await _on_staff_response(
        ctx,
        StaffAssignResponse(
            patient_id=patient_id,
            staff_id=chosen_nurse,
            accepted=True,
            role="nurse",
            flow_id="chat-1",
        ),
    )
    doctor_addr, doctor_req = ctx.sent[-1]
    assert isinstance(doctor_req, StaffAssignRequest) and doctor_req.role == "doctor"

    # Hop 7: doctor → finish
    chosen_doc = doctor.find_available_doctor(store, specialty)
    assert chosen_doc is not None
    doctor.assign_doctor(store, chosen_doc, patient_id, bed_id=chosen_bed)
    ctx.sent.clear()
    await _on_staff_response(
        ctx,
        StaffAssignResponse(
            patient_id=patient_id,
            staff_id=chosen_doc,
            accepted=True,
            role="doctor",
            flow_id="chat-1",
        ),
    )
    # Gate released
    orch._complete_command.assert_called_once_with(ctx, "chat-1")

    # State: patient record has the expected care_team
    prec = store.get(patient.patient_key(patient_id))
    assert prec["care_team"] == [chosen_nurse, chosen_doc]
    assert prec["assigned_bed"] == chosen_bed


@pytest.mark.asyncio
async def test_duplicate_response_is_noop(store):
    """A second PatientIntakeResponse for a finished flow is silently dropped. @spec INTAKE-IDEM-001"""
    ctx = FakeContext()
    _flow(store)  # not registered — simulates a completed/stale flow
    # Do NOT register the flow → it's already been cleaned up after completion
    patient_id, record, _ = admissions.intake(
        store, "Jordan Lee", "chest pain", {"spo2": 96}, "MRN-0005"
    )
    msg = PatientIntakeResponse(
        patient_id=patient_id, record=record, created=True, flow_id="chat-1"
    )
    await _on_intake_response(ctx, msg)
    # No sends: the flow is not in intake_flows, so it's a no-op
    assert len(ctx.sent) == 0
