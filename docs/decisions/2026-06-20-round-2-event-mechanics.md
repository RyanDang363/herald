# Round 2 Event Mechanics — Staff/Oxygen/Summary/Replay (2026-06-20)

**Status:** Accepted. **Owner:** Evan (agents layer).
**Builds on:** [Round 1 event-flow decisions](2026-06-20-event-flow-decisions.md) ·
**Traces to:** [LLD](../llds/er-twin-core.lld.md) · [EARS specs](../specs/er-events-specs.md) · [plan](../plans/2026-06-20-er-twin-core.plan.md) · [README/HLD](../../README.md)

Second-order mechanics for the three demo events + replay export. Stays inside the fixed architecture
(one process / one `Bureau`; only the Orchestrator public; deterministic `USE_MOCK`; `InMemoryStore`
first; Pika MCP external post-processing). **No new message fields** — all implementable with
Orchestrator logic, existing state fields, and one optional state-only field (`needs_restock`).

## Decisions at a glance

| Gap | Decision |
|---|---|
| A Staff capacity | Nurse = single active patient (unavailable after one). Doctor available while `load < 3`. No auto-freeing in the demo. |
| B Oxygen nurse2 | Seed `nurse1` busy with `p2`, leaving `nurse2` free for the oxygen dispatch. |
| C Oxygen swap | Swap `o2_1 → o2_2`; restore patient `spo2 = 96`; move dispatched nurse to bed-3 and mark unavailable. |
| D In-flight dispatch | Orchestrator `in_flight_o2_dispatches: dict[equipment_id, flow_id]`; the bed (and the rest of the multi-hop context) lives on `oxygen_flows[flow_id]`. Clear only after response + state mutation + chat/replay emitted. |
| E Locate semantics | `near_location` advisory; pick any available same-type unit with `supply_level >= 50`, sorted highest-supply then id. |
| F Summary | State-derived counts; add active-O2-alert line if in flight; append "Most urgent: …" when any active acuity ≤ 2. |
| G Replay granularity | Log milestone actions (success **and** failure milestones), not every message. |
| H Replay brief output | Write `out/{incident_id}.json` AND copy latest to `out/incident_replay_brief.json`. |
| I Discharge | No discharge flow in the demo; `discharged` stays a guard/test-only state. |

---

## A — Staff capacity model

```python
NURSE_CAPACITY = 1       # a nurse goes available=False after accepting one active assignment
DOCTOR_LOAD_CAP = 3      # a doctor stays available while load < 3; accepting increments load
```

Nurse becomes unavailable after one patient (matches INTAKE-FLOW-008). Doctor is load-based
(INTAKE-FLOW-011): accepting increments `load` and only flips `available=False` at `load >= 3`. The
generous cap avoids spuriously hitting INTAKE-ERR-004 ("no doctor available") in the core demo. No
auto-freeing (no discharge event — Gap I).

## B — Deterministic `nurse2` for oxygen *(updates Round 1 Gap 5 baseline)*

```python
nurse1 = {"id": "nurse1", "available": False, "location": "bed-3", "assignments": ["p2"]}
nurse2 = {"id": "nurse2", "available": True,  "location": "nurses-station", "assignments": []}
```

Leaving only `nurse2` free makes both the isolated oxygen command and the cumulative run name nurse2,
matching the scripted narrative.

> **Ordering nuance.** If intake runs *before* oxygen it will consume `nurse2` (the only free nurse),
> after which an isolated oxygen command correctly hits the "no staff available" path (OXY-ERR-?? /
> INTAKE-ERR-003 style). For the polished scripted line "Dispatched nurse-2", run **oxygen before
> intake**, or reset state between demos. The system stays correct in any order; only the exact canned
> nurse id depends on order.

## C — Oxygen swap mutations (on accepted dispatch of `o2_2` to `bed3`)

```python
o2_2["in_use_by"] = "p2"; o2_2["location"] = "bed-3"
o2_1["in_use_by"] = None; o2_1["location"] = "storage"; o2_1["needs_restock"] = True  # state-only field
bed3["equipment"] = ["o2_2"]
p2["vitals"]["spo2"] = 96
nurse2["available"] = False; nurse2["location"] = "bed-3"
nurse2["assignments"].append("oxygen_dispatch:bed3")
```

`needs_restock` is an optional state-only field (no message-contract change). Gives the replay a clear
before/after and visibly resolves the alert.

## D — In-flight dispatch tracking (OXY-IDEM-001)

```python
in_flight_o2_dispatches: dict[str, str] = {}   # equipment_id -> flow_id, Orchestrator memory
oxygen_flows: dict[str, OxygenFlow] = {}        # flow_id -> per-flow context (bed, units, nurse, session)
# on dispatch start: in_flight_o2_dispatches["o2_1"] = flow.flow_id   # the bed is flow.bed_id
# clear ONLY after: StaffDispatchResponse accepted -> swap mutation done -> chat/replay emitted -> del
```

Clear-on-completion (not on-response): state may not be updated at response time, so a duplicate alert
could otherwise slip in. Duplicate alert for an id already in the dict → ignored, optional note
"O2 dispatch already in progress for bed-3."

> **Refinement (hardening pass, cascaded below).** The dispatch map keys on `flow_id`, not `bed_id`,
> because the oxygen event is correlated across hops by a `flow_id` threaded through every message
> (LLD §6). The bed and the rest of the multi-hop context live on `oxygen_flows[flow_id]`; so the set
> of beds with an active alert is `[oxygen_flows[fid].bed_id for fid in in_flight_o2_dispatches.values()
> if fid in oxygen_flows]` (this is what the §F summary's active-O2-alert line consumes). Keying on
> `flow_id` lets overlapping or autonomous alerts coexist without one clobbering another.

## E — Equipment locate semantics

`near_location` is advisory for the demo. Candidate filter + deterministic sort:

```python
candidate.type == request.type and candidate.in_use_by is None
and candidate.supply_level is not None and candidate.supply_level >= 50
# sort: highest supply_level first, then id ascending  ->  o2_2 wins
```

Log the source location for narrative ("Located replacement unit o2-2 in storage.").

## F — Summary template (state-derived, USE_MOCK)

```python
active_patients = count(status in {"waiting","in_triage","admitted","in_treatment"})
occupied_beds   = count(bed.status == "occupied")
free_nurses     = count(nurse.available is True)
active_o2_alerts = len(in_flight_o2_dispatches)
urgent_patients  = [p for active p if p.acuity <= 2]
```

```text
{active_patients} patients active, {occupied_beds} beds occupied, {free_nurses} nurse(s) free. {alert_summary}{urgent_summary}
```
- `alert_summary`: "No critical alerts." | "1 active O2 alert on bed-3."
- `urgent_summary`: "" | " Most urgent: Jordan Lee (ESI-2)."
- Empty ER: "Nothing currently happening in the ER — no active patients, no occupied beds, and no critical alerts."

## G — Replay event-log granularity (milestones, incl. failures)

```text
intake  : intake_received, record_created, patient_bound, triaged, bed_assigned,
          nurse_assigned, doctor_paged, intake_complete
          (fail) patient_capacity_reached, no_bed_available, no_nurse_available, no_doctor_available
oxygen  : oxygen_drop_simulated, alert_raised, unit_located, nurse_dispatched,
          oxygen_swap_complete, oxygen_event_complete
          (fail) duplicate_alert_ignored, no_replacement_unit_available, no_dispatch_nurse_available
summary : summary_generated
```
Each line: `{seq, event, actor, action, target, detail}` (LLD §9 contract).

## H — Replay brief derivation + multi-event output

```python
def severity_from_acuity(a): return {1:"critical",2:"high",3:"medium"}.get(a, "low")
# oxygen: use the patient on the affected bed; if none, severity="medium", patient=null

VISUAL_STYLE = {
  "patient_intake":   "clean cinematic ER intake and triage replay, realistic hospital operations",
  "low_oxygen_alert": "urgent but non-graphic hospital operations replay showing rapid oxygen response",
  "er_status_summary":"clean hospital command-center status visualization",
}
```
Write `out/{incident_id}.json` (history) **and** copy the latest to `out/incident_replay_brief.json`
(the fixed input the Phase P Pika script reads). E.g. `out/low_oxygen_alert-0001.json` + the latest copy.

## I — Discharge

No discharge trigger in the demo. `discharged` stays a guard/test-only state (keep the existing
DOMAIN-STATE-003 invariant test). Do **not** implement `Discharge*` messages, pool unbind, or bed
release.

---

## Canned-summary reconciliation (doc clarity)

Because `nurse1` is now pre-busy (Gap B), the **state-derived** summary differs from the old static
TEAM.md string — and that is fine (decision F: real state wins):
- After baseline only: `2 patients active, 1 bed occupied, 1 nurse free. No critical alerts.`
- After admitting Jordan Lee: `3 patients active, 2 beds occupied, 0 nurse(s) free. Most urgent: Jordan Lee (ESI-2).`

The legacy static string `"3 patients active, 2 beds occupied, 1 nurse free."` in the TEAM USE_MOCK
table / Phase-1 `MOCK_REPLIES["summary"]` is now **illustrative only**; Phase 5 replaces it with the
state-derived template.

## Code placement (implementing phases)

| Artifact | Location | Phase |
|---|---|---|
| `NURSE_CAPACITY`, `DOCTOR_LOAD_CAP`, capacity logic | `nurse.py` / `doctor.py` + Orchestrator | 3 |
| `nurse1` busy baseline, `needs_restock` | `seed_baseline` in `main.py` | 3 |
| `in_flight_o2_dispatches`, swap mutation, locate sort | `orchestrator.py` / `equipment.py` | 4 |
| State-derived summary template | `orchestrator.py` | 5 |
| Milestone log set, `severity_from_acuity`, `VISUAL_STYLE`, per-incident + latest file | `orchestrator.py` / `replay.py` | R |

## Cascade performed on 2026-06-20
- **Round 1 doc:** Gap 5 baseline updated — `nurse1` now busy with `p2` (Gap B); `o2_1.needs_restock`.
- **LLD:** §2 Nurse/Doctor capacity note + Equipment `needs_restock`; §6 in-flight O2 dispatch tracking;
  §9 oxygen-swap state mutation, milestone log set, brief derivation (severity/visual_style),
  per-incident + latest file output. Header links this doc.
- **EARS:** `OXY-FLOW-005` (swap specifics), `SUMM-FLOW-002` (alert + urgent lines), `REPLAY-LOG-001`
  (milestone granularity incl. failures) amended. No new spec ids (mechanics, not new behaviors).
- **Tests:** none now — these mechanics belong to unbuilt Phases 3/4/5/R; their tests honor this doc.

## Cascade update — Phase 4 hardening refinement (2026-06-20)

- **Gap D refined code→doc:** `in_flight_o2_dispatches` keys on `flow_id` (not `bed_id`); the bed and
  multi-hop context moved to `oxygen_flows[flow_id]`. Driven by the `flow_id`-keyed multi-hop oxygen
  correlation + full-lifecycle `CommandGate` added during the post-Phase-4 hardening (so overlapping or
  autonomous alerts can't collide; late/duplicate responses are no-ops). The LLD §6 already reflected
  this (`dict[equipment_id, flow_id]` + `oxygen_flows`); this doc (Gap D) and the `low-oxygen-alert`
  arrow doc were the lagging copies, now reconciled. Gap F's `active_o2_alerts` count is unchanged
  (`len(in_flight_o2_dispatches)`); the summary derives the alert *beds* via `oxygen_flows[fid].bed_id`.
