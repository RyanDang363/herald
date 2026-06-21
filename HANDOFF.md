# Handoff: ER Twin — wire the merged components + real-time end-to-end test

You're picking up a 24h Fetch.ai hackathon build. Four feature branches were just integrated onto
`main` (core agents + Redis layer + Iris memory + EHR loader + dashboard). Everything is GREEN in
isolation — **116 passed, 11 skipped, ruff clean** — but the components are NOT wired together yet.
Your job: wire them, then run the whole thing live (real Redis + Iris + dashboard + ASI:One chat) and
fix what breaks in reality. Read this whole prompt, then the files it names, before touching code.

## 0. Read first, in order
1. `CLAUDE.md` — LOCKED architecture + hard rules (one Bureau, only Orchestrator public, USE_MOCK
   deterministic, synthetic data, Pika never called from er_twin/).
2. `STATUS.md` — live tracker. The blocker line lists exactly the pending wiring.
3. `docs/arrows/index.yaml` — arrow graph. `agent-memory`, `patient-ehr`, `dashboard` are **PARTIAL**
   (infra built, integration pending); the 6 core arrows + `redis-store` are OK. Each PARTIAL arrow's
   `next:` names the precise integration spec to satisfy.
4. `docs/specs/er-events-specs.md` — EARS specs. Targets: `MEM-FLOW-001/002`, `EHR-FLOW-001/002`,
   and the dashboard `DASH-SYS-002/003` in `docs/specs/dashboard-specs.md`.
5. `docs/llds/er-twin-core.lld.md` (§4 store, §6 idempotency incl. MRN dedupe note, §7) and
   `docs/llds/dashboard.lld.md` (fixture↔Redis seam).
6. **Fetch.ai requirement docs** — `fetch-ai-documentation/fetchai-hackathon-req.md` and
   `fetch-ai-documentation/fetch-ai-overview-transcript.md`. The mandatory deliverable is the
   Orchestrator reachable from **ASI:One** via an Agentverse mailbox (Chat Protocol). Confirm exactly
   what judging needs (agent registered, discoverable, chat round-trips) before you call it done.

## 1. What's already there (DON'T rebuild — wire these)
- `er_twin/storage.py` → `make_store()` returns `RedisStore(REDIS_URL)` when `REDIS_URL` set AND
  `USE_MOCK` false, else `InMemoryStore`. `RedisStore` + `InMemoryStore` both implement
  `StorageInterface` (get/set/update/list_ids/publish).
- `er_twin/memory.py` → `make_memory()` returns `IrisMemory(...)` when all `AGENT_MEMORY_*` set AND
  `USE_MOCK` false, else `NoopMemory`. Interface: `record_event(text)`, `recall(query) -> list[str]`.
- `er_twin/ehr.py` → `build_live_record(mrn, name, chief_complaint, vitals)`, `next_mrn()`,
  `find_active_patient_by_mrn(store, mrn)`, `register_new_patient(...)`. Master fixture at
  `fixtures/ehr_master.json` (path from `settings.ehr_master_path`).
- `er_twin/protocols.py` → `PatientIntakeRequest` already has `mrn: str = ""`.
- `er_twin/config.py` → knobs: `use_mock`, `redis_url`, `agent_memory_*`, `ehr_master_path`,
  `dashboard_source` ("fixture"|"redis").
- `dashboard/datasource.py` → `get_store()` already returns `RedisStore(REDIS_URL)` when
  `dashboard_source == "redis"`, else the JSON fixture store. `dashboard/server.py` (FastAPI),
  `orchestrator_client.py`, `sim.py`, `static/` UI all exist.

## 2. The gap (what to wire) — TDD + @spec annotations
**A. main.py uses the factories (foundation for everything else).**
   - `er_twin/main.py` does `store = InMemoryStore()`. Change to `store = make_store()` and create
     `memory = make_memory()`. Inject memory into the Orchestrator (add `orch.set_memory(memory)`
     mirroring the existing `orch.set_store`). Keep the deterministic seed/baseline behavior.
   - Precedence: **USE_MOCK=true ⇒ InMemoryStore + NoopMemory** (zero-dep demo),
     **USE_MOCK=false + REDIS_URL/AGENT_MEMORY_* set ⇒ live Redis + Iris.** This is already how the
     factories behave — main.py just has to call them.

**B. Iris memory wiring (MEM-FLOW-001/002).** In `er_twin/agents/orchestrator.py`:
   - After each event reaches its terminal reply (intake confirm, oxygen swap complete, summary), call
     `memory.record_event(<one-line outcome>)` (MEM-FLOW-001). The replay milestone strings are a good
     source of the text.
   - In the summary branch, BEFORE building the summary, call `memory.recall(<query>)` and fold recalled
     facts into the output (MEM-FLOW-002). Under NoopMemory `recall` returns `[]` so the template path
     is unchanged — keep that graceful.
   - Keep it non-fatal: a memory backend error must never crash a command (wrap like `_emit_replay`).

**C. EHR enrichment wiring (EHR-FLOW-001/002).**
   - Orchestrator intake branch: extract an MRN from the chat text if present (regex), put it on
     `PatientIntakeRequest.mrn`; empty string otherwise (EHR-FLOW-001).
   - `er_twin/agents/admissions.py`: call `build_live_record(mrn, name, chief_complaint, vitals)` to
     produce the EHR-enriched record before persisting; mint via `next_mrn()` when mrn empty
     (EHR-FLOW-002). Dedupe by MRN via `find_active_patient_by_mrn` (LLD §6 updated note), falling back
     to name+chief_complaint. Don't break the existing `INTAKE-IDEM-001` behavior/tests.

**D. Dashboard shares the live store.** When agents run with `USE_MOCK=false` (Redis), set
   `DASHBOARD_SOURCE=redis` so `dashboard/datasource.get_store()` reads the SAME Redis the agents write.
   Verify `er:events` published by `ReplayRecorder` shows up in the dashboard's event feed
   (DASH-SYS-002/003). If the key schema differs (`er:{entity}:{id}` vs dashboard expectations),
   reconcile — the dashboard LLD claims the same `er:{entity}:{id}` convention.

## 3. Environment (secrets live in `.env`, which is GITIGNORED — never print/commit them)
`.env` has: `REDIS_URL` SET (Redis Cloud), `AGENT_MEMORY_BASE_URL/STORE_ID/API_KEY` SET (Iris),
`ASIONE_API_KEY` BLANK, `FAL_KEY` BLANK, `USE_MOCK=true`.
Implications:
- Real Redis + Iris ARE available for live testing — flip `USE_MOCK=false` to exercise them.
- With `ASIONE_API_KEY` blank and `USE_MOCK=false`, intent resolution still works: `resolve_command`
  catches the `_resolve_via_llm` RuntimeError and falls back to the deterministic mock lookup. Summary
  LLM synthesis falls back to the template. So you can run live Redis/Iris/dashboard WITHOUT an ASI:One
  key — just no real LLM. (If an ASI:One key gets added, implement `_resolve_via_llm` for real — ties to
  the deferred `ORCH-LLM-001`.)
- Never echo secret values in logs, commits, or the transcript.

## 4. Real-time end-to-end test plan (the actual deliverable)
1. **Unit gate:** `uv run pytest -q` stays green. `uv run ruff check .`
2. **Live Redis boot:** `USE_MOCK=false uv run python -m er_twin.main` → confirm it connects to Redis
   (no InMemoryStore), 18 agents boot, Orchestrator logs its Agentverse inspector URL + "Manifest
   published successfully". `WARNING: Agent mailbox not found` is expected until the one-time connect.
3. **Agentverse/ASI:One connect (MANDATORY):** open the inspector URL, connect the mailbox once, then
   chat the three trigger phrases from ASI:One:
   - "A new patient arrived with chest pain" → intake confirmation
   - "Bed 3's patient oxygen is dropping" → oxygen swap (real async messaging showcase)
   - "Show me what's happening in the ER" → status summary
   Verify each returns a chat reply AND mutates Redis (inspect keys) AND records to Iris.
4. **Dashboard live:** `DASHBOARD_SOURCE=redis` + run `dashboard/server.py` (uvicorn) against the SAME
   Redis. Trigger an event via chat → watch the dashboard reflect the state change + event feed.
5. **Replay:** after an event, confirm `out/incident_replay_brief.json` + `out/pika_prompt.md` are
   written. (Pika render is operator pre-flight — `scripts/run_pika_*.ps1`, needs Claude CLI + Pika
   auth; spends credits. Not required for wiring.)

## 5. Conventions (this repo is strict)
- **IDD cascade:** if intent changes, update LLD/spec FIRST then code. As each wiring lands, flip the
  spec marker `[ ]→[x]` with a `# @spec <ID>` annotation in code + a test.
- **TDD:** failing test (tagged `# @spec`) → minimal wiring → green. Pure functions over
  `StorageInterface`/`MemoryInterface` are unit-testable without a live Bureau (the proven pattern).
- **arrow-maintenance:** when wiring is green, run `/arrow-maintenance` to move `agent-memory`,
  `patient-ehr`, `dashboard` from PARTIAL → OK.
- Branch per task, small PRs into main. End commit messages with the Co-Authored-By trailer.

## 6. Guardrails
- Keep the green tests passing; USE_MOCK=true must still run zero-dependency (InMemoryStore+Noop).
- Memory/EHR/Redis failures must degrade gracefully (NoopMemory, fixture, template) — never crash a
  chat command. The demo must survive a dead backend.
- Don't rewrite the factories/modules in §1 — they're built and tested. Wire them.
- Synthetic data only. Don't commit `.env`. Don't call Pika from er_twin/.

## 7. Definition of done
- main.py uses make_store()/make_memory(); memory + EHR wired into Orchestrator/Admissions; MEM-FLOW-*
  and EHR-FLOW-* specs `[x]` + annotated + tested.
- `USE_MOCK=false` boot connects to live Redis + Iris; all 3 events round-trip from ASI:One chat and
  mutate Redis; dashboard (DASHBOARD_SOURCE=redis) reflects them.
- `uv run pytest` green; `uv run ruff check .` clean; arrows updated; STATUS.md + plan ticked.
- Then surface: the deferred real ASI:One LLM (`ORCH-LLM-001`) if a key is added, and the Pika operator
  pre-flight for the final replay media.
