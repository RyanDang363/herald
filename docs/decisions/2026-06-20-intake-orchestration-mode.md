# Intake Orchestration Mode — Hybrid (in-process canonical + async showcase) (2026-06-20)

**Status:** Accepted. **Owner:** Evan (agents layer).
**Traces to:** [LLD §5/§6](../llds/er-twin-core.lld.md) · [EARS specs](../specs/er-events-specs.md) · [plan](../plans/2026-06-20-er-twin-core.plan.md) · [README/HLD](../../README.md)
**Resolves:** the open Phase 3 question — keep intake as in-process orchestration, or convert it to
real async uAgent messaging? Stays inside the fixed architecture (one process / one Bureau; only the
Orchestrator public; deterministic USE_MOCK; in-memory store first).

## Decision — disciplined hybrid

1. **Keep the in-process `run_intake(store, …)` as the canonical, tested transaction engine and the
   demo-safe fallback.** It stays the source of truth for branch/idempotency logic; the 15 intake
   tests are not weakened or deleted.
2. **The low-oxygen event (Phase 4) is the mandatory real-async-messaging showcase.** The
   EquipmentAgent must autonomously emit `LowSupplyAlert`; the Orchestrator handles
   alert → locate → dispatch via separate `@on_message` handlers. This carries the Fetch.ai
   "agents messaging agents" proof — intake does not have to.
3. **Async intake is a timeboxed enhancement only**, behind a feature flag `INTAKE_MODE=direct|async`
   (default `direct`). Entity handlers call the **same pure domain functions** already tested — the
   async wrapper adds orchestration/correlation, never new business logic. If async intake is not
   green in rehearsal, leave `INTAKE_MODE=direct` and demo agent-to-agent messaging via oxygen.

Priority order: **(1) preserve working direct intake → (2) finish real async oxygen → (3) only then
attempt async intake → (4) use async intake in the demo only if green in rehearsal.**

## Why not fully rewrite intake now
A 6-step async intake state machine is the "purest" story but a risky use of hackathon hours against
an already-working, fully-tested path. The oxygen event is *naturally* async (autonomous alert →
coordinated response), so the autonomous-agent story is covered without gambling the intake demo.

## Feature flag
`config.Settings.intake_mode` (env `INTAKE_MODE`), default `"direct"`. **Inert until async intake
lands** — added now so the demo can switch modes without a code change (the rehearsal fallback). The
chat handler will branch on it once the async path exists; today only `direct` is wired.

## Async intake correlation design (when built)
Commands are serialized (one in flight — ORCH-SYS-003), so no distributed workflow engine is needed —
**one active flow object** on the Orchestrator:

```python
@dataclass
class IntakeFlow:
    chat_sender: str
    chat_session_id: str | None
    name: str; chief_complaint: str; vitals: dict
    patient_id: str | None = None
    record: dict | None = None
    acuity: int | None = None; specialty: str | None = None
    bed_id: str | None = None; nurse_id: str | None = None; doctor_id: str | None = None
    notes: list[str] = field(default_factory=list)
# orchestrator: self.active_intake: IntakeFlow | None = None
```

Step chain (each arrow = `ctx.send` then a separate `@on_message` handler advances `active_intake`):
`PatientIntakeResponse → bind → TriageResponse → BedAssignResponse → Nurse StaffAssignResponse →
(acuity ≤ 2) Doctor StaffAssignResponse → finalize`.

Finalize: build confirmation, emit replay milestones, send `ChatMessage` to `chat_sender`, clear
`active_intake`, release the command gate.

Correlation needs **no contract change**: serialized commands + `patient_id` on responses + the
responding agent's sender address (nurse vs doctor) are sufficient. Add a stall timeout → graceful
chat error, then fall back to direct.

**Highest-value steps to show as real messages** (if only partially converting): Admissions, Triage,
Bed, Nurse/Doctor. Lowest value: the pooled-PatientAgent bind (architecturally needed, undramatic) —
keep it a direct call if time is tight.

## Demo narrative (honest + defensible)
> "Intake is a deterministic, tested orchestration over agent-owned domain logic. The oxygen alert
> demonstrates true autonomous uAgent messaging — an EquipmentAgent emits the alert and the
> Orchestrator coordinates other agents in response. If time allows, intake also runs through the same
> async pattern behind a feature flag."

## Cascade performed on 2026-06-20
- **config:** `Settings.intake_mode` (`INTAKE_MODE`, default `direct`); `.env.example` documents it.
- **EARS:** INTAKE "P3 transport note" reframed — `INTAKE_MODE=direct` is canonical, async is the
  optional enhancement; OXY section notes Phase 4 is the mandatory async showcase.
- **Plan:** Phase 3 marked canonical-direct; Phase 4 marked the async-messaging proof; this doc linked.
- **STATUS / arrows:** open transport question resolved → hybrid; `patient-intake` `next` and
  `low-oxygen-alert` `next` updated.
