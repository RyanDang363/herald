# Arrow: domain-invariants

The entity agents (PatientAgent pool, beds, nurses, doctors, equipment), their seeded state in the
shared store, and the cross-cutting domain invariants (DK1–DK3) plus patient-pool binding.

## Status

**OK** — 2026-06-20. Phase 2 complete and green: 9 new unit tests (4 pool + 5 invariant) + 18 prior =
27/27 pass, `ruff check .` clean, all 16 agents boot in one Bureau (deterministic seed-derived
addresses). All active DOMAIN specs implemented; `INTAKE-BIND-002` implemented; `INTAKE-BIND-003` is
partial (pool-exhaustion detection done, Orchestrator-side report owned by `patient-intake` in Phase 3).

_Re-checked 2026-06-20 (event-flow decision cascade): HLD unchanged. LLD §2 Patient gained `specialty`
+ canonical vitals keys, but this arrow's code seeds only the **pool** (`er:patientagent:{slot}`) and
bed/staff/equipment inventory — it never seeds or handles patient **clinical records** — so the §2
patient-schema change is downstream-neutral here (it lands in `patient-intake`, Phase 3). The clean
`init_state` seed is unchanged; the Gap 5 `seed_baseline` mid-shift layer is additive and Phase-3-owned.
No drift._

## References

| Type | Location |
|------|----------|
| HLD — entities as agents, domain knowledge DK1–DK3 | [README.md](../../README.md) |
| LLD — §2 (entity state schemas + Patient Pool), §4 (Redis key schema), §7 (pool decision) | [docs/llds/er-twin-core.lld.md](../llds/er-twin-core.lld.md) |
| EARS — DOMAIN-STATE-001/002/003, INTAKE-BIND-002/003 | [docs/specs/er-events-specs.md](../specs/er-events-specs.md) |
| Tests | [tests/test_domain_invariants.py](../../tests/test_domain_invariants.py), [tests/test_patient_pool.py](../../tests/test_patient_pool.py) |
| Code | [er_twin/agents/patient.py](../../er_twin/agents/patient.py), [bed.py](../../er_twin/agents/bed.py), [nurse.py](../../er_twin/agents/nurse.py), [doctor.py](../../er_twin/agents/doctor.py), [equipment.py](../../er_twin/agents/equipment.py), [main.py](../../er_twin/main.py) |

## Architecture

**Purpose:** Model every physical ER entity as a uAgent that owns its state in the shared store, and
enforce the confirmed domain invariants as pure, testable guards.

**Key Components:**
1. PatientAgent pool (`patient.py`) — `PATIENT_COUNT=3` per-instance agents; `bind_slot`/`find_idle_slot`
   over `er:patientagent:{slot}`; each agent's `PatientBindRequest` handler binds its own slot.
2. BedAgent pool (`bed.py`) — `er:bed:{id}`; `assign_patient_to_bed` is the guarded mutation for
   DOMAIN-STATE-001 + 002 (idempotent); `release_bed`.
3. Nurse / Doctor / Equipment (`nurse.py`/`doctor.py`/`equipment.py`) — state seed + availability /
   specialty / low-supply helpers; request handlers deferred to Phases 3–4.
4. `main.seed_state` + `build_bureau` — one shared `InMemoryStore`, deterministic pre-run seeding,
   all 16 agents in one Bureau (ORCH-SYS-001).

## EARS Coverage

| Category | Spec IDs | Implemented | Deferred | Gaps |
|----------|----------|-------------|----------|------|
| Domain invariants | DOMAIN-STATE-001/002/003 | 3 | 0 | 0 |
| Patient pool binding | INTAKE-BIND-002 | 1 | 0 | 0 |
| Patient pool exhaustion | INTAKE-BIND-003 | partial | 0 | Orchestrator report (Phase 3) |

**Summary:** 4 of 4 fully-owned active specs implemented; `INTAKE-BIND-003` partial — pool detection
done here, the chat report + no-triage behavior belongs to `patient-intake`.

## Key Findings

1. **Invariants enforced as pure functions, not in handlers** — `bed.assign_patient_to_bed`
   ([bed.py:55](../../er_twin/agents/bed.py#L55)) carries DOMAIN-STATE-001 ([:61](../../er_twin/agents/bed.py#L61))
   and DOMAIN-STATE-002 ([:65](../../er_twin/agents/bed.py#L65)); `patient.can_triage`
   ([patient.py:70](../../er_twin/agents/patient.py#L70)) carries DOMAIN-STATE-003. All idempotent /
   reject-not-raise. Unit-tested directly with an `InMemoryStore`.
2. **PatientBindRequest handler verified registered** — `build_agents` uses `agent.on_message(M)(fn)`
   (closure form); confirmed the `PatientBindRequest` schema digest lands in the agent's
   `_signed_message_handlers`, identical to the proven stub decorator form.
3. **State seeding is synchronous and pre-run** — `main.seed_state` writes all entity records before
   `bureau.run()`, avoiding any async startup-ordering race; initial seed is all-available/empty
   (the docs/TEAM.md fixture is a post-intake snapshot, not the seed).
4. **Equipment availability is type-dependent** — `equipment.is_available` treats consumables
   (oxygen, must be free *and* above threshold 50) differently from devices (free via `in_use_by`),
   per LLD §2. Feeds Event 2 in Phase 4.

## Work Required

### Must Fix
_None — fully-owned specs are coherent._

### Should Fix
_None._

### Nice to Have
1. `INTAKE-BIND-003` completes when `patient-intake` (Phase 3) adds the Orchestrator "patient capacity
   reached" report + no-triage on `find_idle_slot → None`. Re-audit both arrows then.
