# Team Coordination — ER Twin

Single source of truth for who builds what and how we work in parallel. Pair this with the
[implementation plan](plans/2026-06-20-er-twin-core.plan.md), [LLD](llds/er-twin-core.lld.md),
and [EARS specs](specs/er-events-specs.md).

## Ownership map (3 devs)

Fill in names. Tracks map to the phases in the implementation plan.

| Track | Owner | Files | Plan phases |
|---|---|---|---|
| **Agents** — all agent logic (critical path) | **Evan** | `er_twin/main.py`, `er_twin/addresses.py`, `er_twin/replay.py`, `er_twin/agents/orchestrator.py`, `er_twin/agents/stub.py`, `er_twin/agents/{admissions,triage,patient,bed,nurse,doctor,equipment}.py`, all `tests/test_event_*.py`, `tests/test_domain_invariants.py`, `tests/test_patient_pool.py`, `tests/test_replay.py`, `scripts/build_pika_prompt.py`, `scripts/run_pika_identity_check.ps1`, `scripts/run_pika_replay.ps1`, `scripts/run_pika_keyframes.ps1`, `scripts/capture_replay_frames.py`, `scripts/pika_replay_operator.md`, `scripts/demo.md` | Phase 1, 2, 3, 4, 5, R, R+, P |
| **Data-driven replay UI** (LLD §9.1) — shares the dashboard | **Evan** (+ dashboard dev) | `dashboard/static/floor.js` (extracted from `app.js`), `dashboard/static/replay.{html,js}`, `dashboard/static/library.{html,js}`, replay/library routes in `dashboard/server.py`, replay/library tests in `tests/test_dashboard.py` | R+ |
| **Redis layer** — storage backend | _dev 2_ | `er_twin/storage.py` (`RedisStore` implementation only — `InMemoryStore` already scaffolded), `tests/test_storage.py` (extend with `RedisStore` contract tests) | Phase 6 |
| **Dashboard** — admin UI | _dev 3_ | `dashboard/` (FastAPI server + HTML/JS frontend reading store state) | Stretch |

> **Phase 0 is already done** — `protocols.py`, `config.py`, `storage.py` (interface + `InMemoryStore`),
> `addresses.py`, `pyproject.toml`, and `.env.example` are scaffolded and on `main`.
> All three devs can pull and start immediately.

> **Merge point:** Dev 2 (`RedisStore`) merges into `er_twin/storage.py` independently — the
> `StorageInterface` is already defined, so no coordination needed until Phase 6 swap.
> Dev 3 (dashboard) works against the mock JSON fixture below; final wiring is one function call.

## Dashboard mock fixture (Dev 3 starting point)

Dev 3 builds the UI against this hardcoded JSON shape (from LLD §2). When Dev 1's agents are
ready, replace the fixture with a real store read — the schema is identical.

> **Vitals keys standardized (2026-06-20, decision R1):** canonical keys are
> `{heart_rate, blood_pressure, resp_rate, spo2, temperature_f, pain_score}` (was `{hr, bp, spo2, temp_c}`).
> `patient.specialty` is also now part of the patient record. See
> [docs/decisions/2026-06-20-event-flow-decisions.md](decisions/2026-06-20-event-flow-decisions.md).

```json
{
  "patients": [
    {"id": "p1", "name": "Jordan Lee", "status": "admitted", "acuity": 2, "specialty": "cardiology",
     "chief_complaint": "chest pain",
     "vitals": {"heart_rate": 102, "blood_pressure": "138/88", "resp_rate": 20, "spo2": 94, "temperature_f": 98.8, "pain_score": 7},
     "assigned_bed": "bed1", "care_team": ["nurse1", "doc1"]}
  ],
  "beds": [
    {"id": "bed1", "status": "occupied", "occupied_by": "p1", "specialty": "cardiology"},
    {"id": "bed2", "status": "available", "occupied_by": null, "specialty": "general"},
    {"id": "bed3", "status": "available", "occupied_by": null, "specialty": "general"},
    {"id": "bed4", "status": "available", "occupied_by": null, "specialty": "trauma"}
  ],
  "nurses": [
    {"id": "nurse1", "available": false, "location": "bed1", "assignments": ["p1"]},
    {"id": "nurse2", "available": true,  "location": "triage", "assignments": []}
  ],
  "doctors": [
    {"id": "doc1", "specialty": "cardiology", "available": false, "assignments": ["p1"]},
    {"id": "doc2", "specialty": "general",    "available": true,  "assignments": []}
  ],
  "equipment": [
    {"id": "o2_1", "type": "oxygen", "supply_level": 45, "in_use_by": null, "location": "storage"},
    {"id": "o2_2", "type": "oxygen", "supply_level": 88, "in_use_by": "p1", "location": "bed1"},
    {"id": "defib_1", "type": "defibrillator", "supply_level": null, "in_use_by": null, "location": "nurses-station"}
  ]
}
```

## Phase 0 first — hard rule

`protocols.py`, `config.py`, `storage.py`, `addresses.py` are **shared imports**. Dev 1 builds
Phase 0 and merges it to `main` **before** dev 2 and dev 3 start agent code. Until then nobody can
`import` the message models, so everyone is blocked. Phase 0 is the unblock.

## Git workflow — feature branches + PRs

- Branch per task: `dev1/orchestrator-skeleton`, `dev2/bed-agent`, `dev3/intake-flow`.
- Small PRs into `main`; one teammate skims and merges.
- `git pull --rebase origin main` before opening a PR to avoid conflicts.
- **Shared-write files** — `er_twin/main.py` and `er_twin/protocols.py` are the only files multiple
  people touch. Ping the group chat before editing either; keep edits append-only when possible.
- Never commit `.env` (it is gitignored). Update `.env.example` when adding a new variable.

## Shared `USE_MOCK` contract

When `USE_MOCK=true`, the Orchestrator skips the *external* services — keyword intent lookup instead of
the ASI:One LLM (spec `ORCH-LLM-003`), `InMemoryStore` instead of Redis, `NoopMemory` instead of Iris —
but still runs the real agent flow over deterministically seeded state. The strings below are
**illustrative / fallback only** (see the note after the table); the actual replies are state-derived
and deterministic. Lets everyone test without an `ASIONE_API_KEY`. Keep the trigger phrases exact.

| Trigger phrase | Intent | Mock response |
|---|---|---|
| `A new patient MRN-0004 arrived with chest pain` | intake | `Admitted Jordan Lee (MRN-0004, chest pain). Triage ESI-2. Assigned bed-1 + nurse-1; paged Dr. Smith (cardiology).` |
| `A new patient arrived with chest pain` | intake (walk-in, no MRN) | `Admitted walk-in patient (MRN minted). Triage ESI-2. Assigned bed-1 + nurse-1.` |
| `Bed 3's patient oxygen is dropping` | oxygen | `Low O2 on bed-3 (88%). Dispatched nurse-2 with replacement unit o2-2. ETA ~15s.` |
| `Show me what's happening in the ER` | summary | `3 patients active, 2 beds occupied, 1 nurse free. No critical alerts.` |
| `ping` | ping | `pong from stub-agent` |

> **MRN in trigger phrases:** including an MRN lets returning patients have their history loaded automatically. Walk-in triggers (no MRN) are also valid — the system mints a sequential MRN.

The mock response is the *fallback string only*. Real agent handlers still run the actual flow;
mock just bypasses the LLM intent-resolution call.

## The judging demo (7 steps)

The architecture exists to make this loop work. One-liner: _Fetch.ai coordinates the ER response;
ASI:One exposes the public chat interface; StorageInterface/Redis records the event trace; Claude
Code CLI invokes Pika MCP to turn that trace into replay media._

1. Judge chats with **ASI:One**.
2. ASI:One reaches our **Agentverse-registered OrchestratorAgent** (inside the single Bureau — the only public surface).
3. Orchestrator triggers a real **local Bureau event** (intake / oxygen / summary) — in-process, same Bureau.
4. ER agents coordinate and **update state + the `er:events` log**.
5. Orchestrator **replies in chat** with what happened (incl. a `Replay captured → /replay/{incident}` link).
6. System emits a **Pika-ready replay brief** (`out/incident_replay_brief.json` + `out/pika_prompt.md`) **and** a full-state **snapshot timeline** (`out/replay/{incident}.json`) for the data-driven replay (LLD §9.1).
7. **Data-driven replay (preferred):** `python -m scripts.capture_replay_frames {incident}` (Playwright) → keyframe PNGs → **`scripts/run_pika_keyframes.ps1`** → Claude Code CLI → Pika `generate_keyframes_video` → clip URL written back into `out/replay/{incident}.json` as `video_url`. The gated **`/library`** page lists every incident with its clip; **`/replay/{incident}`** plays the reconstruction in-browser as the offline fallback. (Text-brief `scripts/run_pika_replay.ps1` is the documented fallback.)

Steps 1–6 are pure Fetch.ai (the judging path). Step 7 is automated creative post-processing — Pika
MCP is never called from inside the uAgents runtime, only by the Claude Code CLI. The `/replay` and
`/library` pages reuse the dashboard's `floor.js`, so the replay map matches the live floor exactly.

## Demo-day roles

| Role | Who | Job |
|---|---|---|
| Driver | _dev ?_ | Types the 3 exact trigger phrases into ASI:One chat |
| Narrator | _dev ?_ | Explains the agent coordination to judges |
| Backup | _dev ?_ | Watches logs; flips `USE_MOCK=true` if the network/API fails |

## Daily sync points

- After Phase 0 merges: confirm everyone can `import er_twin.protocols`.
- After Phase 1: orchestrator chat ping round-trips in-process to the stub in the same Bureau (`python -m er_twin.main`).
- Hour 16 checkpoint: all 3 events fire end-to-end with `USE_MOCK=true`. Freeze scope; cut anything
  not in the 3-event demo.

## EHR loader handoff (Dev 1 — AdmissionsAgent wiring)

The EHR slice is **done** — `er_twin/ehr.py`, `fixtures/ehr_master.json` (20 patients), and
`scripts/build_ehr.py` are implemented and all 21 tests pass.

**One-call wiring in AdmissionsAgent's intake handler:**

```python
from er_twin.ehr import build_live_record, find_active_patient_by_mrn

async def handle_intake(ctx, msg: PatientIntakeRequest, store):
    # 1. MRN dedupe — don't create a second record for an active visit.
    existing_id = find_active_patient_by_mrn(store, msg.mrn)
    if existing_id:
        return PatientIntakeResponse(patient_id=existing_id, record=store.get(f"er:patient:{existing_id}"))

    # 2. Build EHR-enriched record (mrn, history, new_patient — no patient_id/status yet).
    record = build_live_record(msg.mrn, msg.name, msg.chief_complaint, msg.vitals)

    # 3. Assign visit identity and persist.
    patient_id = _next_patient_id(store)           # your sequential id logic
    record["patient_id"] = patient_id
    record["status"] = "waiting"
    record["id"] = patient_id
    store.set(f"er:patient:{patient_id}", record)

    return PatientIntakeResponse(patient_id=patient_id, record=record)
```

Key rules:
- `build_live_record` populates `mrn`/`history`/`new_patient` but **not** `patient_id`/`status`.
- `find_active_patient_by_mrn` works on both `InMemoryStore` and `RedisStore` through the `StorageInterface`.
- The EHR loader **always runs** (local file IO) — it is not affected by `USE_MOCK`.
- For walk-in patients (no MRN in chat), pass `mrn=""` and the system mints one automatically.

**EHR master fixture:** `fixtures/ehr_master.json` has 20 pre-loaded patients (`MRN-0001`..`MRN-0020`).
Use any MRN in that range in your demo trigger phrase to see a returning patient with full history.

**Verification:** `uv run pytest tests/test_ehr.py` — 21 tests, all offline.

## Redis layer handoff (Dev 1 — agents wiring)

Phases 6 + 7 are **done** — `RedisStore`, `make_store()`, `IrisMemory`, `NoopMemory`, and
`make_memory()` are all implemented and smoke-tested against Redis Cloud.

**One-line wiring in the Orchestrator and agents:**

```python
# In er_twin/agents/orchestrator.py (Dev 1 adds this)
from er_twin.storage import make_store
from er_twin.memory import make_memory

store = make_store()    # RedisStore when REDIS_URL set, InMemoryStore otherwise
memory = make_memory()  # IrisMemory when AGENT_MEMORY_* set, NoopMemory otherwise
```

Then call:
- `store.set("er:patient:p1", {...})` / `store.get(...)` / `store.update(...)` in handlers
- `store.publish("er:events", json.dumps({...}))` after each completed ER event
- `memory.record_event("Jordan admitted to bed1 with chest pain")` after each event
- `memory.recall("recent oxygen alerts")` in the status summary handler

**Verification:** `uv run python scripts/redis_smoke.py` → all four checks must be OK before the demo.
