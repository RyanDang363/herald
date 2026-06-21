# Arrow: patient-intake

Event 1 — chest-pain intake: admissions (id mint + dedupe) → pool bind → triage (acuity + specialty)
→ specialty-aware bed assignment → nurse + (acuity ≤ 2) doctor → chat confirmation, with the ERR/IDEM
paths. Composed by `orchestrator.run_intake` over the shared store; status transitions owned by the
Orchestrator (decision Gap 8).

## Status

**OK** — 2026-06-20 (PARTIAL on transport). Phase 3 complete and green: 15 intake tests + 27 prior =
42/42 pass, `ruff check .` clean, 18 agents boot, intake runs end-to-end from the chat command
in-process (admits p3 → bed-1 + Nurse Chen; paged Dr. Smith). All 23 active INTAKE-* specs `[x]`.

**Transport (decided — hybrid):** `INTAKE_MODE=direct` (canonical/demo-safe) runs the hops in-process
(`run_intake` invokes each entity's pure domain function over the shared store). `INTAKE_MODE=async`
(optional/timeboxed, inert until built) would use uAgent `*Request`/`*Response` envelopes calling the
same pure functions. The mandatory async-messaging proof is the oxygen event, not intake. See
[decisions/2026-06-20-intake-orchestration-mode.md](../decisions/2026-06-20-intake-orchestration-mode.md).

_Re-checked 2026-06-20 (intake-orchestration-mode cascade): HLD unchanged; decision recorded +
cascaded to config (`INTAKE_MODE`, inert), specs/plan/STATUS. No spec markers changed; no drift._

## References

| Type | Location |
|------|----------|
| HLD — Event 1, agents-as-entities | [README.md](../../README.md) |
| LLD — §3 intake contracts, §5 async pattern, §6 idempotency | [docs/llds/er-twin-core.lld.md](../llds/er-twin-core.lld.md) |
| Decisions — Gap 1/2/3/8 (R1), R2-A capacity, R2-B baseline | [Round 1](../decisions/2026-06-20-event-flow-decisions.md) · [Round 2](../decisions/2026-06-20-round-2-event-mechanics.md) |
| EARS — 23 active INTAKE-* specs | [docs/specs/er-events-specs.md](../specs/er-events-specs.md) |
| Tests | [tests/test_event_intake.py](../../tests/test_event_intake.py) (15) |
| Code | [orchestrator.py](../../er_twin/agents/orchestrator.py) (`run_intake`), [admissions.py](../../er_twin/agents/admissions.py), [triage.py](../../er_twin/agents/triage.py), [bed.py](../../er_twin/agents/bed.py), [nurse.py](../../er_twin/agents/nurse.py), [doctor.py](../../er_twin/agents/doctor.py), [main.py](../../er_twin/main.py) (`seed_baseline`) |

## Architecture

**Purpose:** Admit a patient end-to-end and produce a chat confirmation, enforcing capacity, specialty
routing, idempotency, and graceful error paths.

**Key Components:**
1. `admissions.intake` — `p{n}` mint via `er:counter:patient`; active dedupe by name + chief_complaint.
2. `triage.assess`/`triage` — deterministic complaint→(acuity, specialty); discharge guard (DOMAIN-STATE-003).
3. `bed.find_available_bed` — specialty match → `general` fallback → None.
4. `nurse.assign_nurse` (single-patient) / `doctor.assign_doctor` (load < 3) — capacity per R2-A, idempotent.
5. `orchestrator.run_intake` — composes the above in INTAKE-FLOW order, owns status transitions, builds the milestone log + confirmation; `MOCK_INTAKE` + `DISPLAY_NAMES` for the demo.
6. `main.seed_baseline` — mid-shift demo state (R2-B: nurse1 busy → oxygen later picks nurse2).

## EARS Coverage

| Category | Spec IDs | Implemented | Deferred | Gaps |
|----------|----------|-------------|----------|------|
| Flow | INTAKE-FLOW-001..011 | 11 | 0 | 0 |
| Bind | INTAKE-BIND-001/002/003 | 3 | 0 | 0 |
| State | INTAKE-STATE-001/002 | 2 | 0 | 0 |
| Errors | INTAKE-ERR-001..004 | 4 | 0 | 0 |
| Idempotency | INTAKE-IDEM-001/002 | 2 | 0 | 0 |

**Summary:** 23 of 23 active INTAKE specs implemented + tested. Transport realized in-process (open
follow-up to async messages — does not change the tested logic).

## Key Findings

1. **In-process orchestration over the shared store** — `run_intake` ([orchestrator.py](../../er_twin/agents/orchestrator.py)) is the single coordinator; entity agents own their domain functions. Deterministic + fully unit-tested; the autonomous-messaging upgrade is tracked, not lost.
2. **Capacity model is asymmetric (R2-A)** — nurse single-patient (`available=False` after one); doctor load-based (`available` while `load < 3`). Both assignment fns are idempotent (INTAKE-IDEM-002).
3. **Patient enumeration via `list_ids("patient")`** — fulfils the Gap 3 `er:index:patient` intent for InMemoryStore (prefix index); RedisStore can back it with a set later. Ids mint from `er:counter:patient`; discharged patients stay indexed (none in the demo).
4. **Baseline makes events order-robust (R2-B)** — `seed_baseline` leaves only nurse2 free so the Phase 4 oxygen dispatch names nurse2; intake adds Jordan Lee as p3.

## Work Required

### Must Fix
_None — all INTAKE specs implemented + tested._

### Should Fix
1. **Transport decision (tracked):** convert orchestrator↔entity intake hops to explicit async uAgent `*Request`/`*Response` messages (heads-up #3 async model) if the autonomous-messaging demo is wanted. Pure functions stay the shared truth; only the transport changes. No logic/test impact.

### Nice to Have
2. Replay milestone lines are produced by `run_intake` (list) but not yet published to `er:events` — wired in Phase R.
