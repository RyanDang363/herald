# Arrow: core-agents

**Status**: UNMAPPED  
**Audited**: —  
**HLD SHA at audit**: —

## References

| Artifact | Path |
|---|---|
| HLD | [`README.md`](../../README.md) — full agent topology |
| LLD | [`docs/llds/er-twin-core.lld.md`](../llds/er-twin-core.lld.md) — §3 (agents), §4 (protocols), §5 (Bureau wiring) |
| EARS | [`docs/specs/er-events-specs.md`](../specs/er-events-specs.md) — all `ORCH-*`, `INTAKE-*`, `OXY-*`, `SUMM-*`, `DOMAIN-*` specs |
| Code | `er_twin/agents/` (not yet created), `er_twin/main.py` (not yet created) |
| Tests | `tests/` — agent behavior tests not yet written |

## Domain

Everything the `redis-store`, `agent-memory`, and `patient-ehr` arrows provide infrastructure for. This arrow owns all agent-to-agent behavior — the uAgents Bureau, the OrchestratorAgent (Chat Protocol, ASI:One LLM, mailbox), and all domain agents (Stub, Admissions, Triage, Patient pool, Bed, Nurse, Doctor, Equipment).

**Owned by Dev 1.**

## Spec Coverage

### ORCH — Orchestrator & System Foundation

| Spec ID | Status | Notes |
|---|---|---|
| `ORCH-CHAT-001` | `[ ]` | Orchestrator mailbox + Chat Protocol registration |
| `ORCH-CHAT-002` | `[ ]` | ChatMessage → ChatAcknowledgement + reply |
| `ORCH-SYS-001` | `[ ]` | All non-Orchestrator agents in a Bureau |
| `ORCH-SYS-002` | `[x]` | Deterministic seed addresses — done in `er_twin/addresses.py` |
| `ORCH-SYS-003` | `[ ]` | Chat serialization (one command at a time) |
| `ORCH-LLM-001` | `[ ]` | ASI:One intent resolution |
| `ORCH-LLM-002` | `[ ]` | ASI:One timeout/rate-limit fallback |
| `ORCH-LLM-003` | `[ ]` | `USE_MOCK` hardcoded intent lookup |
| `ORCH-LLM-004` | `[ ]` | Unknown intent → clarifying chat reply |
| `ORCH-SKEL-001` | `[ ]` | Ping → stub → reply loop (first-slice proof) |

### INTAKE — Event 1: Patient Intake

| Spec ID | Status | Notes |
|---|---|---|
| `INTAKE-FLOW-001` | `[ ]` | Orchestrator sends PatientIntakeRequest |
| `INTAKE-FLOW-002` | `[ ]` | AdmissionsAgent builds + persists record (storage layer `[x]`, agent handler `[ ]`) |
| `INTAKE-BIND-001/002/003` | `[ ]` | PatientAgent pool bind |
| `INTAKE-FLOW-003` | `[ ]` | Orchestrator sends TriageRequest |
| `INTAKE-FLOW-004` | `[ ]` | TriageAgent assigns acuity + persists |
| `INTAKE-FLOW-005` | `[ ]` | Orchestrator sends BedAssignRequest |
| `INTAKE-FLOW-006` | `[ ]` | BedAgent marks bed occupied |
| `INTAKE-FLOW-007/008` | `[ ]` | Orchestrator + NurseAgent staff assignment |
| `INTAKE-FLOW-010/011` | `[ ]` | Doctor assignment for acuity ≤ 2 |
| `INTAKE-FLOW-009` | `[ ]` | Orchestrator chat confirmation |
| `INTAKE-STATE-001/002` | `[ ]` | Patient status → `admitted`; acuity 1–5 |
| `INTAKE-ERR-001/002/003/004` | `[ ]` | No bed / no nurse / no doctor fallbacks |
| `INTAKE-IDEM-001/002` | `[ ]` | MRN dedup + assignment dedup |

### OXY — Event 2: Oxygen Alert

| Spec ID | Status | Notes |
|---|---|---|
| `OXY-FLOW-001` through `OXY-FLOW-006` | `[ ]` | Full alert → locate → dispatch chain |
| `OXY-ERR-001` | `[ ]` | No replacement unit fallback |
| `OXY-IDEM-001` | `[ ]` | In-flight dispatch dedup |

### SUMM — Event 3: Status Summary

| Spec ID | Status | Notes |
|---|---|---|
| `SUMM-FLOW-001` | `[ ]` | Read all entity state (storage `[x]`, agent caller `[ ]`) |
| `SUMM-FLOW-002` | `[ ]` | ASI:One natural-language summary |
| `SUMM-ERR-001` | `[ ]` | Empty ER message |
| `SUMM-STATE-001` | `[ ]` | Read-only invariant |

### MEM — Agent call sites (module implemented under `agent-memory`)

| Spec ID | Status | Notes |
|---|---|---|
| `MEM-FLOW-001` (call site) | `[ ]` | Orchestrator calls `memory.record_event()` after events |
| `MEM-FLOW-002` (call site) | `[ ]` | Orchestrator calls `memory.recall()` before summary |

### DOMAIN — Cross-cutting Invariants

| Spec ID | Status | Notes |
|---|---|---|
| `DOMAIN-STATE-001` | `[ ]` | One patient per bed |
| `DOMAIN-STATE-002` | `[ ]` | One bed per patient |
| `DOMAIN-STATE-003` | `[ ]` | No triage for discharged patient without new intake |

**1 of ~37 active specs done (ORCH-SYS-002). 36 require agent implementation.**

## Recommended Start Order (Dev 1)

1. **`ORCH-SYS-001` + `ORCH-SKEL-001`** — Bureau up, StubAgent ping loop, Orchestrator registered. Prove in-process messaging works before building any real handlers.
2. **`ORCH-CHAT-001` + `ORCH-CHAT-002`** — Chat Protocol handlers so ASI:One can reach the Orchestrator.
3. **`ORCH-LLM-003`** — `USE_MOCK` intent resolution first; real ASI:One call (`ORCH-LLM-001`) second.
4. **`INTAKE-FLOW-001` → `INTAKE-FLOW-009`** — Full intake chain as the primary demo event.
5. **`OXY-*`** and **`SUMM-*`** — Second and third demo events.

## Blockers

This arrow is blocked by `redis-store`, `agent-memory`, and `patient-ehr` — all three are OK or PARTIAL with ready-to-call APIs. No blockers remain for Dev 1 to start.
