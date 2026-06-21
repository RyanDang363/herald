# EARS Specs — ER Twin Core Events

**Traces to:** [LLD — ER Twin Core](../llds/er-twin-core.lld.md) → [README (HLD)](../../README.md)
**Status markers:** `[ ]` active gap (not yet implemented) · `[x]` implemented · `[D]` deferred

Spec ID format: `{FEATURE}-{TYPE}-{NNN}`. Features: `ORCH` (orchestrator/chat/system), `INTAKE` (Event 1), `OXY` (Event 2), `SUMM` (Event 3), `REPLAY` (incident replay bridge), `DOMAIN` (cross-cutting invariants). Types: `CHAT`, `LLM`, `SYS`, `SKEL`, `FLOW`, `BIND`, `ERR`, `IDEM`, `STATE`, `LOG`, `BRIEF`.

---

## ORCH — Orchestrator, Chat & System Foundation (first slice)

- [x] **ORCH-CHAT-001** — When the system starts, the OrchestratorAgent shall register with a mailbox and include the Chat Protocol, making it reachable from ASI:One. *(P1: `orchestrator.py` `mailbox=True` + `Protocol(spec=chat_protocol_spec)`; boot logs "Starting mailbox client" + "Manifest published successfully: AgentChatProtocol")*
- [x] **ORCH-CHAT-002** — When the OrchestratorAgent receives a `ChatMessage`, it shall return a `ChatAcknowledgement` and a `ChatMessage` reply to the sender. *(P1: `handle_chat` acks first, then `_send_chat`)*
- [x] **ORCH-SYS-001** — The system shall run all agents — the OrchestratorAgent (with mailbox) and every entity agent — inside a single uAgents Bureau process. *(ubiquitous invariant; spike-proven. Two-process split is the documented fallback only.)* *(P1: `main.build_bureau`)*
- [x] **ORCH-SYS-002** — When the system starts, it shall compute each agent's address from its deterministic seed and expose those addresses as startup constants. *(no runtime discovery)* *(P1: `addresses.seed_for`/`*_ADDRESS`; agents seeded with `seed_for(...)`)*
- [x] **ORCH-SYS-003** — While a chat command is being processed, the OrchestratorAgent shall defer any newly received chat command until the current one has produced a reply. *(serialization — LLD §6)* *(P1: `CommandGate` asyncio lock around `handle_chat` processing; one-in-flight)*
- [D] **ORCH-LLM-001** — When the OrchestratorAgent receives a natural-language command, it shall call the ASI:One LLM to resolve the command into a structured intent identifying the target event. *(deferred past P1: USE_MOCK is the P1 path; real ASI:One client wired in Phase 5. `_resolve_via_llm` is the seam.)*
- [x] **ORCH-LLM-002** — If the ASI:One call times out, is rate-limited, or errors, then the OrchestratorAgent shall return a hardcoded fallback response and continue without crashing. *(P1: `resolve_command` catches any `_resolve_via_llm` failure and falls back to the mock lookup)*
- [x] **ORCH-LLM-003** — Where `USE_MOCK` is enabled, the OrchestratorAgent shall resolve intents from a hardcoded lookup instead of calling the ASI:One LLM. *(P1: `resolve_intent` / `resolve_command` when `settings.use_mock`)*
- [x] **ORCH-LLM-004** — If the resolved intent matches no known event, then the OrchestratorAgent shall return a clarifying chat message and shall not dispatch any agent messages. *(P1: `handle_chat` sends `CLARIFICATION` for `"unknown"`, no dispatch)*
- [x] **ORCH-SKEL-001** — When the OrchestratorAgent resolves a ping intent, it shall send a `PingRequest` to the stub agent and return the stub's `PingResponse` text to the chat sender. *(first-slice proof of the loop)* *(P1: `handle_chat` ping path → `stub.on_ping` → `orchestrator.on_pong` relays via `SessionSenders` + pending FIFO)*

---

## INTAKE — Event 1: Patient Intake

Trigger: *"A new patient arrived with chest pain"*

> **Transport (decision 2026-06-20-intake-orchestration-mode — hybrid).** `INTAKE_MODE=direct` (the
> canonical, demo-safe default) realizes these flows by in-process orchestration: `orchestrator.run_intake`
> composes each entity agent's pure domain function over the shared store (admissions/triage/bed/nurse/
> doctor) and owns the patient status transitions (decision Gap 8). Behaviours, state outcomes,
> idempotency, and error paths below are implemented and unit-tested (`tests/test_event_intake.py`,
> 15 tests) and run live from the chat command — `[x]` = behaviour implemented + tested.
> The literal "sends/receives `*Request`/`*Response`" wording is the message-envelope transport;
> `INTAKE_MODE=async` (a **timeboxed, optional** enhancement) realizes it as explicit uAgent messages
> whose handlers call the **same** pure functions. The mandatory real-async-messaging showcase is the
> low-oxygen event (OXY-FLOW-007 → autonomous `LowSupplyAlert`), so intake need not carry that proof.

- [x] **INTAKE-FLOW-001** — When the OrchestratorAgent resolves a patient-intake intent, it shall send a `PatientIntakeRequest` to the AdmissionsAgent containing the patient name, chief complaint, and vitals. *(P3: `run_intake` → `admissions.intake`; `MOCK_INTAKE` supplies name/vitals)*
- [x] **INTAKE-FLOW-002** — When the AdmissionsAgent receives a `PatientIntakeRequest` for a new patient, it shall create a patient record with status `waiting`, persist it to `er:patient:{id}`, and return a `PatientIntakeResponse` with the assigned `patient_id`. *(P3: `admissions.intake`, `p{n}` via `er:counter:patient`)*
- [x] **INTAKE-BIND-001** — When the OrchestratorAgent receives a `PatientIntakeResponse` for a new patient, it shall send a `PatientBindRequest` to bind an idle pooled PatientAgent and hydrate it with the record. *(P3: `run_intake` → `patient.find_idle_slot`/`bind_slot`)*
- [x] **INTAKE-BIND-002** — When an idle PatientAgent receives a `PatientBindRequest`, it shall set its `bound_to` to the patient id, load the record, and return a `PatientBindResponse` with `bound=true`. *(P2: `patient.bind_slot` + the per-agent `PatientBindRequest` handler)*
- [x] **INTAKE-BIND-003** — If no PatientAgent is idle when a `PatientBindRequest` is needed, then the OrchestratorAgent shall leave the patient record in `waiting`, report "patient capacity reached" to the chat, and not proceed to triage. *(P3: `run_intake` capacity branch — `patient.find_idle_slot → None`)*
- [x] **INTAKE-FLOW-003** — When a patient has been bound to a PatientAgent, the OrchestratorAgent shall send a `TriageRequest` to the TriageAgent for that patient. *(P3: `run_intake` → `triage.triage`)*
- [x] **INTAKE-FLOW-004** — When the TriageAgent receives a `TriageRequest`, it shall assign an acuity level between 1 and 5 **and a required care specialty**, persist both to the patient record, and return a `TriageResponse` carrying `acuity` and `specialty`. *(P3: `triage.assess`/`triage`; specialty per decision Gap 1)*
- [x] **INTAKE-FLOW-005** — When the OrchestratorAgent receives a `TriageResponse`, it shall send a `BedAssignRequest` to the BedAgent for the patient's required specialty. *(P3: `run_intake` → `bed.find_available_bed(specialty)`)*
- [x] **INTAKE-FLOW-006** — When the BedAgent receives a `BedAssignRequest` and a matching-specialty bed is available, it shall mark that bed `occupied`, record `occupied_by`, and return a `BedAssignResponse` with `success=true` and the `bed_id`. *(P3: `bed.find_available_bed` + `assign_patient_to_bed`)*
- [x] **INTAKE-FLOW-007** — When a bed is successfully assigned, the OrchestratorAgent shall send a `StaffAssignRequest` to an available NurseAgent for that patient and bed. *(P3: `run_intake` → `nurse.find_available_nurse`/`assign_nurse`)*
- [x] **INTAKE-FLOW-008** — When a NurseAgent accepts a `StaffAssignRequest`, it shall set itself unavailable, add the patient to its assignments, and return a `StaffAssignResponse` with `accepted=true`. *(P3: `nurse.assign_nurse`, `NURSE_CAPACITY=1`)*
- [x] **INTAKE-FLOW-010** — When a patient's acuity is 2 or lower (more urgent), the OrchestratorAgent shall also send a `StaffAssignRequest` to an available DoctorAgent for that patient and bed. *(P3: `run_intake` acuity ≤ 2 branch → `doctor.find_available_doctor(specialty)`)*
- [x] **INTAKE-FLOW-011** — When a DoctorAgent accepts a `StaffAssignRequest`, it shall increment its patient load, add the patient to its assignments, and return a `StaffAssignResponse` with `accepted=true`. *(P3: `doctor.assign_doctor`, `DOCTOR_LOAD_CAP=3`)*
- [x] **INTAKE-FLOW-009** — When intake completes, the OrchestratorAgent shall return a chat confirmation naming the patient, assigned bed, and the assigned care team (nurse, and doctor when one was paged). *(P3: `_format_intake_confirmation` + `DISPLAY_NAMES`)*
- [x] **INTAKE-STATE-001** — When a patient is admitted to a bed, the system shall set the patient record status to `admitted`. *(state-driven outcome)* *(P3: `run_intake` sets `admitted` after bed assign — decision Gap 8)*
- [x] **INTAKE-STATE-002** — The system shall represent patient acuity as an integer from 1 (most urgent) to 5 (least urgent). *(ubiquitous invariant — ESI scale)* *(P3: `triage.assess` returns 1–5)*
- [x] **INTAKE-ERR-001** — If no bed matching the required specialty is available, then the BedAgent shall attempt to assign a `general` bed before reporting failure. *(P3: `bed.find_available_bed` specialty → general fallback)*
- [x] **INTAKE-ERR-002** — If no bed is available at all, then the patient record shall remain in status `waiting` and the OrchestratorAgent shall report "no bed available" to the chat, without retrying. *(P3: `run_intake` no-bed branch)*
- [x] **INTAKE-ERR-003** — If no NurseAgent accepts the assignment, then the patient shall remain assigned to the bed but unstaffed, and the OrchestratorAgent shall report "no staff available" to the chat, without retrying. *(P3: `run_intake` no-nurse branch)*
- [x] **INTAKE-ERR-004** — If acuity is 2 or lower and no DoctorAgent is available, then the OrchestratorAgent shall complete intake with the nurse only and note "no doctor available" in the chat confirmation, without retrying. *(P3: `run_intake` no-doctor branch + `_format_intake_confirmation`)*
- [x] **INTAKE-IDEM-001** — If a `PatientIntakeRequest` matches an existing non-discharged patient by name and chief complaint, then the AdmissionsAgent shall return the existing `patient_id` and shall not create a second record. *(P3: `admissions._find_active_duplicate`)*
- [x] **INTAKE-IDEM-002** — If a `BedAssignRequest` or `StaffAssignRequest` targets a patient already assigned to that bed or staff member, then the receiving agent shall return the existing assignment with `success`/`accepted=true` and shall not write new state. *(P3: idempotent `bed.assign_patient_to_bed` / `nurse.assign_nurse` / `doctor.assign_doctor`)*

---

## OXY — Event 2: Low Oxygen Alert

Trigger: *"Bed 3's patient oxygen is dropping"*

> **Mandatory async showcase (decision 2026-06-20-intake-orchestration-mode).** Unlike intake, Event 2
> MUST use real async uAgent messaging: the EquipmentAgent autonomously emits `LowSupplyAlert` and the
> Orchestrator handles alert → locate → dispatch in separate `@on_message` handlers. This is the
> project's Fetch.ai "agents messaging agents" proof.

- [x] **OXY-FLOW-007** — When the OrchestratorAgent resolves a low-oxygen intent for a named bed, it shall send a `SimulateOxygenDropRequest` to the EquipmentAgent of the oxygen unit at that bed (rather than synthesizing the alert itself); that agent shall lower its `supply_level` below the threshold and the bed patient's `spo2`. *(scripted demo trigger for the autonomous push — decision Gap 4)* *(P4: `orchestrator.handle_chat` oxygen branch → `address_for(equipment.oxygen_unit_at_bed)`; `equipment._make_simulate_handler` → `simulate_oxygen_drop`)*
- [x] **OXY-FLOW-001** — When an oxygen EquipmentAgent's `supply_level` falls below the low threshold, it shall emit a `LowSupplyAlert` to the OrchestratorAgent with its id, type, level, and location. *(P4: `equipment._make_simulate_handler` `ctx.send(ORCHESTRATOR_ADDRESS, LowSupplyAlert(...))` — autonomous push, verified in `spikes/oxygen_async_flow_spike.py`)*
- [x] **OXY-FLOW-002** — When the OrchestratorAgent receives a `LowSupplyAlert`, it shall send an `EquipmentLocateRequest` for a replacement unit of the same type near the alert location. *(P4: `orchestrator.on_low_supply` → `equipment.locate_replacement` (R2-E sort) → `EquipmentLocateRequest`)*
- [x] **OXY-FLOW-003** — When an EquipmentAgent of the requested type is available near the location, it shall return an `EquipmentLocateResponse` with `available=true` and its id and location. *(P4: `equipment._make_locate_handler` answers for itself via `is_available`)*
- [x] **OXY-FLOW-004** — When a replacement unit is located, the OrchestratorAgent shall send a `StaffDispatchRequest` to a NurseAgent to bring the unit to the target location. *(P4: `orchestrator.on_locate` → `nurse.find_available_nurse` → `StaffDispatchRequest`)*
- [x] **OXY-FLOW-005** — When a NurseAgent accepts a `StaffDispatchRequest`, it shall return a `StaffDispatchResponse` with `accepted=true`, and the system shall apply the swap: the replacement unit → `in_use_by=<patient>` at the bed, the depleted unit → freed/`needs_restock`, the bed's equipment list updated, the patient's `spo2` restored to 96, and the nurse moved to the bed and marked unavailable. *(swap mutations — decision R2-C)* *(P4: `nurse._make_dispatch_handler`; `orchestrator.on_dispatch` → `apply_oxygen_swap` = `equipment.swap_oxygen_unit` + `nurse.dispatch_nurse`)*
- [x] **OXY-FLOW-006** — When the dispatch is confirmed, the OrchestratorAgent shall return a chat status confirmation describing the unit, the dispatched nurse, and the target bed. *(P4: `orchestrator.format_oxygen_confirmation` via `_reply_oxygen`)*
- [x] **OXY-ERR-001** — If no replacement unit of the requested type is available near the location, then the OrchestratorAgent shall report "no available unit" to the chat and shall not dispatch a unit whose own `supply_level` is below the low threshold. *(P4: `equipment.locate_replacement` filters `supply_level >= threshold`; `on_low_supply`/`on_locate` no-replacement branch reports + clears in-flight)*
- [x] **OXY-IDEM-001** — If a `LowSupplyAlert` is received for an equipment id that already has an in-flight dispatch, then the OrchestratorAgent shall not initiate a second dispatch for it. *(P4: `orchestrator.should_start_o2_dispatch` over `in_flight_o2_dispatches`, cleared on completion — decision R2-D)*

---

## SUMM — Event 3: Status Summary

Trigger: *"Show me what's happening in the ER"*

- [x] **SUMM-FLOW-001** — When the OrchestratorAgent resolves a status-summary intent, it shall read the current state of all patients, beds, nurses, doctors, and equipment from the store. *(P5: `build_status_summary` reads via `store.list_ids`/`store.get`; the summary chat branch in `_dispatch_command` reads the store directly — LLD §7)*
- [x] **SUMM-FLOW-002** — When the state has been read, the OrchestratorAgent shall synthesize a natural-language summary and return it to the chat — via the ASI:One LLM when enabled, or a deterministic store-derived template where `USE_MOCK` is set: counts of active patients, occupied beds and free nurses, an active-O2-alert line when a dispatch is in flight, and a "Most urgent: {name} (ESI-{acuity})" line when any active patient has acuity ≤ 2. *(USE_MOCK template — decisions Gap 6 / R2-F; mirrors ORCH-LLM-003)* *(P5: `build_status_summary` template; alert beds derived from `oxygen_flows`/`in_flight_o2_dispatches`; "Most urgent" = lowest acuity ≤ 2, id-ascending tie-break. ASI:One LLM path remains the deferred seam.)*
- [x] **SUMM-ERR-001** — If the ER has no active patients and no occupied beds, then the OrchestratorAgent shall return a "nothing currently happening in the ER" summary rather than an error. *(P5: `build_status_summary` empty-ER early return)*
- [x] **SUMM-STATE-001** — When producing a summary, the OrchestratorAgent shall not mutate any entity state. *(read-only invariant)* *(P5: `build_status_summary` only calls `store.get`/`list_ids`; `test_summary_does_not_mutate_state` snapshots the store before/after)*

---

## REPLAY — Incident Replay Bridge (P3)

The Fetch runtime produces a structured trace; the creative media step is performed externally by
the **Claude Code CLI → Pika MCP** (automated, Alternative A) and is out of EARS scope (it is a
script-driven post-processing step, not autonomous system behavior). These specs cover only what the
uAgents must emit.

- [x] **REPLAY-LOG-001** — When the OrchestratorAgent completes a significant **milestone** during an event, it shall publish a structured JSON line (`seq`, `event`, `actor`, `action`, `target`, `detail`) to the `er:events` channel — at milestone granularity (success and failure milestones per LLD §9), not per internal message. *(LLD §9 event-line contract + milestone set — decision R2-G)* *(PR: `replay.ReplayRecorder.log`; intake publishes `run_intake` milestones, oxygen publishes per async handler into `OxygenFlow.lines`, summary publishes `summary_generated`)*
- [x] **REPLAY-LOG-002** — The system shall order event-log lines by a monotonically increasing per-run `seq` counter and shall not depend on wall-clock time. *(ubiquitous — deterministic, reproducible runs)* *(PR: `ReplayRecorder._seq` monotonic; `build_brief` sorts by `seq`; no timestamp field anywhere in the trace)*
- [x] **REPLAY-BRIEF-001** — When an event completes, the system shall write `out/incident_replay_brief.json` containing `incident_id`, `incident_type`, `title`, `summary`, `severity`, `location`, synthetic `patient`, an ordered `timeline` (with `t` derived from `seq`), `final_state`, `visual_style`, and `pika_outputs_requested`. *(LLD §9 schema)* *(PR: `replay.build_brief` + `write_incident`; `t` from relative `seq`; severity via `severity_from_acuity`; per-incident `out/{incident_id}.json` + latest copy)*
- [x] **REPLAY-BRIEF-002** — When `out/incident_replay_brief.json` has been written, the system shall render `out/pika_prompt.md` — a creative brief derived from it that instructs Pika MCP to use synthetic data only (no gore / real people / PHI), emphasize autonomous coordination, and return the asset URL/ID, `task_id`, tool used, and a short summary. *(PR: `replay.render_pika_prompt` (written inline by `export_incident`); `scripts/build_pika_prompt.py` re-renders from a brief)*
- [x] **REPLAY-BRIEF-003** — If no event has run in the current session, then the system shall not write a replay brief or prompt (no empty artifacts). *(PR: `export_incident` returns None and writes nothing when there are no milestone lines; `_emit_replay` skips when no store/lines)*
- [x] **REPLAY-BRIEF-004** — The system shall set `incident_type` to one of `patient_intake`, `low_oxygen_alert`, or `er_status_summary`, matching the completed event. *(ubiquitous — brief↔event mapping)* *(PR: `replay.INCIDENT_TYPES` maps event→incident_type; `next_incident_id` mints `{type}-{n:04d}`)*

---

## DOMAIN — Ubiquitous Invariants

Confirmed domain constraints (DK1–DK3). Enforced by the relevant agents and asserted in tests.

- [x] **DOMAIN-STATE-001** — The system shall not allow a bed to be occupied by more than one patient at a time. *(DK1)* *(P2: `bed.assign_patient_to_bed` rejects a second occupant; idempotent for the same patient)*
- [x] **DOMAIN-STATE-002** — The system shall not allow a patient to be assigned to more than one bed at a time. *(DK2)* *(P2: `bed.assign_patient_to_bed` rejects a second bed for an already-assigned patient)*
- [x] **DOMAIN-STATE-003** — If a patient's status is `discharged`, then the system shall not triage that patient without a new intake. *(DK3)* *(P2: `patient.can_triage` returns False for discharged; Triage gates on it in Phase 3)*

---

## Consistency Report

**Coverage:** every message contract in LLD §3 and every Event flow in README §Events has ≥1 spec. The first-slice skeleton (LLD §5) is covered by `ORCH-SKEL-001` + `ORCH-SYS-*`. The incident replay bridge (LLD §9) is covered by `REPLAY-*`.

**Out of EARS scope (by design):** Pika MCP media generation is an external, **Claude-Code-CLI-driven** post-processing step (Alternative A; manual VSCode operator is Alternative B, fal.ai is Alternative E) — not autonomous system behavior — so it carries no EARS specs. The boundary the system *does* own (event log + brief/prompt files) is specified by `REPLAY-*`. The CLI invocation contract (allowlist, `permission_denials` check) lives in LLD §9 and the implementation plan, not EARS.

**Idempotency:** state-mutating flows carry sibling `IDEM` specs — intake (`INTAKE-IDEM-001`), oxygen dispatch (`OXY-IDEM-001`), and bed/staff assignment (covered by LLD §6, see open question Q3 below).

**Resolved decisions (2026-06-20):**

- **Patient intake model → Pooled PatientAgents.** PatientAgents are pre-instantiated at startup; intake binds an idle one (`INTAKE-BIND-001/002`, capacity error `INTAKE-BIND-003`). See LLD §2 Patient Agent Pool + §7.
- **Q1 → A.** Acuity range pinned as ubiquitous invariant `INTAKE-STATE-002`.
- **Q2 → B.** High-acuity (≤ 2) intake also pages a doctor: `INTAKE-FLOW-010/011`, error `INTAKE-ERR-004`.
- **Q3 → A.** Assignment idempotency made explicit: `INTAKE-IDEM-002`.
- **DK1–DK3 → all confirmed.** Captured as `DOMAIN-STATE-001/002/003`.

---

*Next phase after approval: implementation plan in `docs/plans/`.*
