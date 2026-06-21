# Arrow: patient-ehr

**Status**: OK  
**Audited**: 2026-06-21  
**HLD SHA at audit**: `8e87478` (integrated-tree README; reconciled from pre-integration `8513c74`)

## References

| Artifact | Path |
|---|---|
| HLD | [`README.md`](../../README.md) — §EHR Integration |
| LLD | [`docs/llds/er-twin-core.lld.md`](../llds/er-twin-core.lld.md) — §EHR Contract |
| EARS | [`docs/specs/er-events-specs.md`](../specs/er-events-specs.md) — `EHR-FLOW-001` through `EHR-ERR-001`, `INTAKE-IDEM-001` |
| Code | `er_twin/ehr.py`, `er_twin/protocols.py`; **integration:** `er_twin/agents/admissions.py` (`intake` enrichment + MRN dedupe), `er_twin/agents/orchestrator.py` (`extract_mrn`, `run_intake` threading) |
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
- **`patient_id`** (`p{n}`, minted from the `er:counter:patient` counter) — visit-scoped runtime identity; unique per admission.

A discharged patient re-admitted gets a **new `patient_id`** but the **same MRN** and their history is reloaded from the EHR fixture.

## Spec Coverage

| Spec ID | Status | Notes |
|---|---|---|
| `EHR-FLOW-001` | `[x]` | `orchestrator.extract_mrn` parses an `MRN-NNNN` token from chat; `run_intake` threads `mrn` into `admissions.intake`. Empty string when absent → mint at build time. |
| `EHR-FLOW-002` | `[x]` | `admissions.intake` calls `build_live_record(mrn, name, chief_complaint, vitals)` and persists the enriched record (history + resolved/minted MRN) to `er:patient:{id}`. |
| `EHR-FLOW-003` | `[x]` | Returning patient path in `build_live_record`; `@spec` annotated in `ehr.py` |
| `EHR-FLOW-004` | `[x]` | New patient path + writeback in `build_live_record`; `@spec` annotated in `ehr.py` |
| `EHR-FLOW-005` | `[x]` | `next_mrn()` called when `mrn` is blank; `@spec` annotated in `ehr.py` |
| `EHR-IDEM-001` | `[x]` | `register_new_patient` no-ops on duplicate MRN; `@spec` annotated in `ehr.py` |
| `EHR-IDEM-002` | `[x]` | Cache refreshed after writeback; `@spec` annotated in `ehr.py` |
| `EHR-ERR-001` | `[x]` | Missing fixture → empty history, no raise; tested in `test_ehr.py` |
| `INTAKE-IDEM-001` | `[x]` | `admissions.intake` checks `find_active_patient_by_mrn` first (returning chart still active), then the name+chief_complaint fallback — both before any new record. |

**8 of 8 active EHR specs implemented — intake fully EHR-enriched.**

## Implementation Findings

`test_ehr.py` covers all three intake paths (returning, new, walk-in), MRN minting, writeback, cache coherence, idempotency, and missing-fixture fallback. The Orchestrator/Admissions integration landed 2026-06-21 (`evan/wire-memory-ehr-dashboard`).

`admissions.intake` now resolves dedupe in order — **MRN match first** (`find_active_patient_by_mrn`, a returning chart still active in the ER), then the **name + chief_complaint fallback** (preserves `INTAKE-IDEM-001` for walk-ins with no MRN) — then enriches via `build_live_record` and persists. `run_intake` and the Orchestrator's intake chat branch thread `mrn` from `extract_mrn(chat_text)`.

`tests/test_integration_wiring.py` covers `extract_mrn`, returning-patient history enrichment, walk-in MRN minting, MRN dedupe, and the name-fallback path. `tests/conftest.py` adds an autouse fixture redirecting `ehr_master_path` to a per-test temp file so intake-time writeback never mutates the committed `fixtures/ehr_master.json`.

**Verified live**: a returning `MRN-0007` intake loaded `{warfarin, atrial fibrillation, penicillin}` into the live Redis `er:patient:{id}` hash, and the same MRN deduped across process runs.

`fixtures/ehr_master.json` is committed and reproducible via `python scripts/build_ehr.py`.

## Remaining Work

None for the demo — intake is fully EHR-enriched and verified live.
