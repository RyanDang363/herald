# Arrow: patient-ehr

**Status**: PARTIAL  
**Audited**: 2026-06-20  
**HLD SHA at audit**: `8513c74`

## References

| Artifact | Path |
|---|---|
| HLD | [`README.md`](../../README.md) — §EHR Integration |
| LLD | [`docs/llds/er-twin-core.lld.md`](../llds/er-twin-core.lld.md) — §EHR Contract |
| EARS | [`docs/specs/er-events-specs.md`](../specs/er-events-specs.md) — `EHR-FLOW-001` through `EHR-ERR-001`, `INTAKE-IDEM-001` |
| Code | `er_twin/ehr.py`, `er_twin/protocols.py` |
| Fixture | `fixtures/ehr_master.json` (20 synthetic patients, MRN-0001 – MRN-0020) |
| Script | `scripts/build_ehr.py` |
| Tests | `tests/test_ehr.py` |
| Config | `er_twin/config.py` — `ehr_master_path` |

## Domain

Loads a mock master EHR at patient intake, enriching the live agent record with chart history (medications, conditions, allergies). Distinguishes returning patients (MRN in master EHR) from new walk-ins (MRN minted on the fly).

### Key functions in `er_twin/ehr.py`

| Function | Purpose |
|---|---|
| `load_master(path)` | Reads and caches `fixtures/ehr_master.json` |
| `get_ehr_record(mrn)` | Looks up a single patient by MRN |
| `next_mrn()` | Mints the next sequential `MRN-NNNN` |
| `register_new_patient(mrn, name, …)` | Writes a stub entry + refreshes cache |
| `build_live_record(mrn, name, chief_complaint, vitals)` | **Main intake entrypoint** — returns full enriched record dict |
| `find_active_patient_by_mrn(store, mrn)` | Returns `patient_id` of non-discharged patient with that MRN |

### MRN vs patient_id

- **MRN** (`MRN-NNNN`) — person-scoped chart identity; survives across visits.
- **`patient_id`** (`p-<uuid>`) — visit-scoped runtime identity; unique per admission.

A discharged patient re-admitted gets a **new `patient_id`** but the **same MRN** and their history is reloaded from the EHR fixture.

## Spec Coverage

| Spec ID | Status | Notes |
|---|---|---|
| `EHR-FLOW-001` | `[ ]` | **Dev 1** — Orchestrator extracts MRN from chat and puts it in `PatientIntakeRequest.mrn` |
| `EHR-FLOW-002` | `[ ]` | **Dev 1** — AdmissionsAgent calls `build_live_record()` before persisting |
| `EHR-FLOW-003` | `[x]` | Returning patient path in `build_live_record`; `@spec` annotated in `ehr.py:159` |
| `EHR-FLOW-004` | `[x]` | New patient path + writeback in `build_live_record`; `@spec` annotated in `ehr.py:167` |
| `EHR-FLOW-005` | `[x]` | `next_mrn()` called when `mrn` is blank; `@spec` annotated in `ehr.py:70` |
| `EHR-IDEM-001` | `[x]` | `register_new_patient` no-ops on duplicate MRN; `@spec` annotated in `ehr.py:97` |
| `EHR-IDEM-002` | `[x]` | Cache refreshed after writeback; `@spec` annotated in `ehr.py:97` |
| `EHR-ERR-001` | `[x]` | Missing fixture → empty history, no raise; tested in `test_ehr.py:78` |
| `INTAKE-IDEM-001` | `[ ]` | **Dev 1** — AdmissionsAgent checks `find_active_patient_by_mrn` before creating new record |

**6 of 8 active EHR specs implemented. 2 require Dev 1 agent wiring.**

## Implementation Findings

21 offline tests in `test_ehr.py` covering all three intake paths (returning, new, walk-in), MRN minting, writeback, cache coherence, idempotency, and missing fixture fallback.

`fixtures/ehr_master.json` is committed to the repo and reproducible via `python scripts/build_ehr.py` if it ever needs to be regenerated.

`PatientIntakeRequest.mrn: str = ""` is already in `protocols.py` — the contract change Dev 1 needs is done.

## Remaining Work

**Dev 1 action required:**

1. **`EHR-FLOW-001`** — In the Orchestrator's chat handler, parse for an MRN token (e.g. regex `MRN-\d+`) in the user message and populate `PatientIntakeRequest.mrn`. If none found, send `""`.

2. **`EHR-FLOW-002` + `INTAKE-IDEM-001`** — In the AdmissionsAgent's `PatientIntakeRequest` handler:

```python
from er_twin.ehr import build_live_record
from er_twin.ehr import find_active_patient_by_mrn

existing_id = find_active_patient_by_mrn(store, req.mrn) if req.mrn else None
if existing_id:
    return PatientIntakeResponse(patient_id=existing_id, status="already_admitted")

record = build_live_record(req.mrn, req.name, req.chief_complaint, req.vitals)
record["patient_id"] = f"p-{uuid4()}"
record["status"] = "waiting"
store.set(f"er:patient:{record['patient_id']}", record)
```

See `docs/TEAM.md §EHR loader handoff` for full wiring notes.
