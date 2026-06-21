# Event-Flow Decisions — Patient Intake, Low Oxygen, Status Summary, Replay (2026-06-20)

**Status:** Accepted. **Owner:** Evan (agents layer).
**Traces to:** [LLD](../llds/er-twin-core.lld.md) · [EARS specs](../specs/er-events-specs.md) · [plan](../plans/2026-06-20-er-twin-core.plan.md) · [README/HLD](../../README.md)

Resolves nine design/documentation gaps surfaced before building Phases 3–R. These refine **how** the
already-specified events behave; they do **not** change the locked architecture (one process / one
`Bureau`; only the Orchestrator public; `InMemoryStore` first, Redis later; Pika MCP only via the
Claude Code CLI post-processing path). Cascaded into the LLD and EARS specs on the same date.

## Decisions at a glance

| Gap | Decision | Contract change |
|---|---|---|
| 1 Specialty source | TriageAgent assigns + returns `specialty`; persisted on the patient record | **Yes** — `specialty` field on `TriageResponse` + on Patient state |
| 2 USE_MOCK intake data | `MOCK_INTAKE` fixture keyed by trigger phrase | No |
| 3 Patient ids / index | AdmissionsAgent owns `er:counter:patient` + `er:index:patient` | No |
| 4 Low-oxygen trigger | Orchestrator sends an internal simulate-drop message; EquipmentAgent then emits `LowSupplyAlert` | **Yes** — new `SimulateOxygenDrop{Request,Response}` |
| 5 Demo state model | Hybrid: clean `init_state` for tests + a `seed_baseline` mid-shift layer for the demo | No (additive seed layer) |
| 6 USE_MOCK summary | Deterministic, store-derived template (no LLM) | No |
| 7 Friendly names | Presentation-only `DISPLAY_NAMES` map in the Orchestrator | No |
| 8 Patient status ownership | Orchestrator owns `waiting → in_triage → admitted → in_treatment` transitions | No |
| 9 Replay seq / incident ids | Orchestrator owns in-memory per-run `seq` + per-type incident counters | No |

The only contract additions are **Gap 1** and **Gap 4**. Everything else is constants, fixtures, or
Orchestrator logic.

---

## Reconciliations (where the input conflicted with existing contracts)

Recorded so the chain stays coherent rather than forking:

- **R1 — Vitals key schema.** The richer schema below is adopted as **canonical** and cascaded into
  LLD §2 and the `docs/TEAM.md` dashboard fixture (legacy `{hr, bp, spo2, temp_c}` retired; `spo2` is
  common to both, so the oxygen narrative is unaffected). Vitals remain an opaque `dict` in the
  message contracts, so no message digest changes.
- **R2 — Equipment availability.** Availability stays modeled by `in_use_by: str|null` (per LLD §2)
  with `equipment.is_available()` deriving the rest from `in_use_by` + `supply_level` vs threshold.
  We do **not** store redundant `available`/`in_use` booleans (two-sources-of-truth drift trap). The
  baseline scenario is expressed as `o2_1.in_use_by="p2"`, `o2_2.in_use_by=None`.
- **R3 — Clean vs baseline seed.** Each entity's `init_state(store)` keeps seeding the **clean** base
  inventory (empty beds, idle pool, available staff) — Phase 2 unit tests depend on this. The
  mid-shift scenario is a separate `seed_baseline(store)` layer applied only by `main.py` for the
  running demo. `EMPTY_ER` = clean seed with no baseline applied (used by summary edge-case tests).

---

## Gap 1 — Specialty source  *(contract change)*

TriageAgent assigns acuity **and** specialty; both persist to the patient record; the Orchestrator
reads `specialty` to drive `BedAssignRequest.required_specialty` and specialty-matched doctor paging.

```python
# protocols.py
class TriageResponse(Model):
    patient_id: str
    acuity: int
    specialty: str = "general"   # NEW (default keeps it backward-compatible)
```

Patient state gains a `specialty` field (LLD §2). For the chest-pain trigger: `acuity=2`,
`specialty="cardiology"`, `status="in_triage"`.

**Demo triage mapping (USE_MOCK / deterministic), chief_complaint → (acuity, specialty):**

| chief_complaint contains | acuity | specialty |
|---|---|---|
| "chest pain" | 2 | cardiology |
| "shortness of breath" / "oxygen" | 3 | general |
| (default) | 3 | general |

## Gap 2 — USE_MOCK intake data

`MOCK_INTAKE`, keyed by the exact trigger phrase, lives next to `MOCK_REPLIES` in `orchestrator.py`.
Canonical vitals keys (R1):

```python
MOCK_INTAKE = {
    "A new patient arrived with chest pain": {
        "name": "Jordan Lee",
        "chief_complaint": "chest pain",
        "vitals": {
            "heart_rate": 112, "blood_pressure": "156/92", "resp_rate": 22,
            "spo2": 96, "temperature_f": 98.6, "pain_score": 8,
        },
    },
}
```

## Gap 3 — Patient ids / index

AdmissionsAgent mints deterministic ids and maintains the index:

```text
er:counter:patient  -> int (starts 0); next id = f"p{counter+1}", increment on create
er:index:patient    -> set/list of all created patient ids
```

Discharged patients **stay** in `er:index:patient` (auditability); active dedupe/summary filter by
`status != "discharged"`. Dedupe key (INTAKE-IDEM-001): `name` + `chief_complaint` among
non-discharged patients.

## Gap 4 — Low-oxygen trigger  *(contract change)*

The chat command initiates the **autonomous** alert via an internal simulate-drop message — the
EquipmentAgent, not the Orchestrator, emits the `LowSupplyAlert`, preserving the "agents act" thesis.

```python
# protocols.py (Event 2 section)
class SimulateOxygenDropRequest(Model):
    bed_id: str
    equipment_id: str | None = None   # default: the oxygen unit at bed_id
    patient_spo2: int = 88
    new_supply_level: int = 45        # below the 50% low threshold

class SimulateOxygenDropResponse(Model):
    bed_id: str
    equipment_id: str
    triggered: bool
```

Flow:

```text
Chat: "Bed 3's patient oxygen is dropping"
  → Orchestrator → SimulateOxygenDropRequest(bed_id="bed3") to the EquipmentAgent at bed-3 (o2_1)
  → EquipmentAgent sets o2_1.supply_level=45 and the bed's patient spo2=88, then emits LowSupplyAlert
  → Orchestrator runs the existing locate → dispatch flow (OXY-FLOW-002..006)
```

## Gap 5 — Demo state model (hybrid baseline)

`seed_baseline(store)` (applied only in `main.py`) layers a mid-shift ER on top of the clean seed so
the oxygen and summary commands work in any order. Canonical vitals (R1); equipment via `in_use_by` (R2).

```python
# Patients (created records; pool binding for these baseline patients is not required for the demo)
p1 = {"id": "p1", "name": "Sam Rivera", "chief_complaint": "observation after minor fall",
      "acuity": 4, "specialty": "general", "status": "in_triage",
      "vitals": {"heart_rate": 84, "blood_pressure": "128/78", "resp_rate": 16,
                 "spo2": 98, "temperature_f": 98.4, "pain_score": 3},
      "assigned_bed": None, "care_team": []}
p2 = {"id": "p2", "name": "Avery Chen", "chief_complaint": "shortness of breath",
      "acuity": 3, "specialty": "general", "status": "in_treatment",
      "vitals": {"heart_rate": 104, "blood_pressure": "136/84", "resp_rate": 24,
                 "spo2": 92, "temperature_f": 99.1, "pain_score": 4},
      "assigned_bed": "bed3", "care_team": ["doc2"]}
# er:counter:patient = 2 after baseline; er:index:patient = ["p1","p2"]

# Bed: bed3 occupied by p2, carrying o2_1
bed3 = {"id": "bed3", "occupied_by": "p2", "status": "occupied", "specialty": "general",
        "equipment": ["o2_1"]}

# Equipment (R2 — in_use_by, no redundant booleans)
o2_1 = {"id": "o2_1", "type": "oxygen", "supply_level": 55, "in_use_by": "p2", "location": "bed-3"}
o2_2 = {"id": "o2_2", "type": "oxygen", "supply_level": 88, "in_use_by": None, "location": "storage"}

# Staff  (nurse1 busy per Round 2 Gap B — leaves only nurse2 free so the oxygen dispatch names nurse2)
nurse1 = {"id": "nurse1", "available": False, "location": "bed-3", "assignments": ["p2"]}
nurse2 = {"id": "nurse2", "available": True,  "location": "nurses-station", "assignments": []}
doc1   = {"id": "doc1", "available": True, "specialty": "cardiology", "load": 0, "assignments": []}
doc2   = {"id": "doc2", "available": True, "specialty": "general",    "load": 1, "assignments": ["p2"]}
```

After Jordan Lee is admitted (cardiology → bed1 + **nurse2** + doc1; nurse1 is pre-busy per Round 2
Gap B), the store-derived summary lands near *"3 patients active, 2 beds occupied, 0 nurse(s) free.
Most urgent: Jordan Lee (ESI-2)."* (real state wins — see Round 2 decision F). `o2_1` starts at 55
(healthy); the
simulate-drop takes it to 45, crossing the threshold and triggering the alert; `o2_2` (88, free) is
the valid replacement (OXY-ERR-001: never dispatch a unit below threshold).

## Gap 6 — USE_MOCK summary (state-derived template)

Deterministic, computed from store counts — no LLM, satisfies SUMM-ERR-001, mutates nothing:

```text
{active_patients} patients active, {occupied_beds} beds occupied, {available_nurses} nurse(s) free. {alert_summary}
```
Empty ER:
```text
Nothing currently happening in the ER — no active patients, no occupied beds, and no critical alerts.
```

## Gap 7 — Friendly names (presentation only)

Ids in state, friendly names in chat via an Orchestrator-only `DISPLAY_NAMES` map:

```python
DISPLAY_NAMES = {
    "p1": "Sam Rivera", "p2": "Avery Chen",
    "nurse1": "Nurse Maya", "nurse2": "Nurse Chen",
    "doc1": "Dr. Smith", "doc2": "Dr. Patel",
    "bed1": "bed-1", "bed2": "bed-2", "bed3": "bed-3", "bed4": "bed-4",
    "o2_1": "oxygen unit o2-1", "o2_2": "replacement unit o2-2",
}
# Newly admitted patients use their intake name (e.g. "Jordan Lee") directly.
```

## Gap 8 — Patient status ownership

The Orchestrator (which sequences the flow) owns status transitions; entity agents own only their own
resource state:

```text
AdmissionsAgent creates patient        -> status = waiting
Orchestrator sends TriageRequest       -> status = in_triage
Orchestrator on successful BedAssign    -> status = admitted
(later care flow)                       -> status = in_treatment
```

## Gap 9 — Replay seq / incident ids

Orchestrator instance state, reset per process run (no wall-clock):

```python
event_seq = 0                 # incremented per published er:events line (monotonic per run)
incident_counters = {"patient_intake": 0, "low_oxygen_alert": 0, "er_status_summary": 0}
# per completed incident: incident_counters[t] += 1; incident_id = f"{t}-{n:04d}"
# timeline display: t = f"00:{seq*5:02d}"  (demo keeps <12 lines per incident, so seq*5 < 60)
```

---

## Code placement (for the implementing phases)

| Artifact | Location | Phase |
|---|---|---|
| `TriageResponse.specialty`, `SimulateOxygenDrop*` | `er_twin/protocols.py` | now (this change) |
| `MOCK_INTAKE`, `DISPLAY_NAMES`, summary template, `event_seq`/`incident_counters` | `er_twin/agents/orchestrator.py` | 3 / 5 / R |
| `seed_baseline(store)` | `er_twin/main.py` (clean `init_state` stays per-entity) | 3 |
| Demo triage mapping | `er_twin/agents/triage.py` | 3 |
| `er:counter:patient`, `er:index:patient` | `er_twin/agents/admissions.py` | 3 |

## Cascade performed on 2026-06-20
- **LLD:** §2 Patient gains `specialty` + canonical vitals keys; §2 Equipment availability note kept
  on `in_use_by` (R2); §3 adds `TriageResponse.specialty` + `SimulateOxygenDrop*`; §9 pins
  seq/incident-id allocation. Decision doc linked.
- **EARS:** `INTAKE-FLOW-004` amended (triage returns specialty); new `OXY-FLOW-007` (simulate-drop
  trigger → autonomous alert); `SUMM-FLOW-002` amended (USE_MOCK state-derived template).
- **Contracts:** `protocols.py` — `specialty` on `TriageResponse`; `SimulateOxygenDrop{Request,Response}`.
- **Shared fixture:** `docs/TEAM.md` vitals keys updated to canonical (R1).
