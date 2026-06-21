# CLAUDE.md

Guidance for Claude (and any AI agent) working in this repository.

## What this project is

**ER Room Digital Twin** — an autonomous digital twin of a hospital emergency room. Every physical entity (patient, nurse, doctor, bed, equipment) is modeled as a **uAgent**. The system runs in **one process / one `Bureau`** (the spike-verified P1 default):

1. a **public OrchestratorAgent** (`mailbox=True`, `publish_agent_details=True`, Chat Protocol) **added to the Bureau** — registered on Agentverse and reachable from **ASI:One**, the only public surface;
2. all private ER entity agents **in the same Bureau** (in-process messaging; no mailbox, no Agentverse profiles).

State lives behind a `StorageInterface` — **`InMemoryStore` is the demo-safe default**; `RedisStore` is an optional later swap. After an event runs, the Orchestrator emits a structured incident trace (`out/incident_replay_brief.json` + `out/pika_prompt.md`) that **Claude Code CLI → Pika MCP** turns into replay media. It's a hackathon build (24h target, Python 3.11+).

> **Why one process:** our spike (`spikes/mailbox_inside_bureau_spike.py`) proves on `uagents==0.25.2` that the Bureau starts a member agent's mailbox client and in-process messaging works — so the riskiest seam is proven. The **two-process** split (standalone Orchestrator + separate Bureau) is the documented **fallback** only, used if ASI:One/Agentverse smoke testing fails. See README → *Architecture Alternatives and Fallbacks*.

- **Full spec / High-Level Design:** [README.md](README.md) — the source of architectural intent.
- **Live development status + hand-off context:** [STATUS.md](STATUS.md) — read this first to know where things stand.

## How we work: spec-driven development

This repo follows **intent-driven development (IDD)** via the `intent-driven-dev` skill. Design intent is captured in docs *before* code, so a multi-person build doesn't drift into mismatched message names and Redis keys.

The arrow of intent: **README (HLD) → LLD/contracts → EARS specs → Tests → Code**

- Design docs live in `docs/llds/`, `docs/specs/`, and `docs/plans/`.
- **Before changing code, verify coherence:** do the EARS specs, tests, and code agree? If intent changed, update the doc *first*, then cascade downward — don't patch code and leave the spec stale.
- Annotate code and tests with `# @spec EVENT-XXX-NNN` comments tracing back to EARS spec IDs.
- Mutation, not accumulation: update docs in place, delete what's obsolete. Docs reflect *current* intent, not history.

Use the full four-phase workflow (HLD → LLD → EARS → Plan) for new features and major changes. For bug fixes and quick changes, skip doc creation but still verify intent coherence first.

## How we work: test-driven development

Follow **TDD whenever practical**, especially for agent message handlers and event flows:

1. Turn the relevant EARS spec into a failing test, tagged `# @spec <SPEC-ID>`.
2. Write the minimal handler/logic to make it pass.
3. Refactor with the test green.

Every state-mutating behavior should have a test, including idempotency (what happens when the same trigger fires twice?). Tests trace to EARS spec IDs so requirements stay verifiable.

When TDD doesn't fit (throwaway spikes, infra wiring, exploratory work), test-after is acceptable — but the behavior must end up covered before a slice is "done."

## Project conventions (RONGERS standards)

- **Language / runtime:** Python 3.11+
- **Agent framework:** `uagents` + `uagents-core` (Bureau for local agents; Chat Protocol on the Orchestrator only)
- **Layout:** single package `er_twin/` with `agents/`, `protocols.py` (shared message `Model`s), `storage.py`, `config.py`, and a **single entry point** — `main.py` (builds one Bureau holding the Orchestrator + all entity agents, then `bureau.run()`)
- **Runtime/version:** Python pinned `>=3.11,<3.13` (3.14 breaks `uagents==0.25.2` event-loop init); construct the chat protocol with `Protocol(spec=chat_protocol_spec)` — there is no importable `chat_proto`; use `network="testnet"` to quiet Almanac warnings
- **Message schemas:** uAgent `Model` classes in shared `protocols.py`, named request/response (e.g. `PatientIntakeRequest` / `PatientIntakeResponse`)
- **State:** Redis hashes keyed `er:{entity}:{id}` (e.g. `er:patient:p1`), behind a `StorageInterface` — start with an in-memory dict, swap to Redis once core events work
- **Config:** `pydantic-settings` reading `.env`; a `USE_MOCK` flag returns hardcoded Orchestrator responses for demo reliability
- **Addresses:** deterministic seed-derived agent addresses set as constants at startup — no runtime discovery
- **Tooling:** `uv` (deps), `ruff` (format + lint), `pytest` (tests)
- **Secrets:** `.env` (never commit) + `.env.example`. Keys: `ASIONE_API_KEY`, `REDIS_URL`, `FAL_KEY`, `AGENT_SEED`

## Hard rules (demo-critical)

- **One process / one Bureau by default (spike-proven).** The public `OrchestratorAgent` (`mailbox=True`) is added to the same `Bureau` as the private entity agents; `er_twin/main.py` is the single entry point. The two-process split (standalone Orchestrator + separate Bureau) is the **fallback** only, if ASI:One/Agentverse smoke testing fails.
- **Async messaging, not request/response.** Handlers `ctx.send` and return; replies arrive in a separate `@on_message` handler. The Orchestrator stores `{session/request id → user sender address}` and replies to chat from the response handler.
- **Only the OrchestratorAgent gets a mailbox / Agentverse registration.** All other agents are local Bureau agents — never try to host them on Agentverse.
- **The demo must be deterministic** — hardcode scripted triggers for the 3 events; no live randomness during judging.
- Keep instance counts small: 3 patients, 2 nurses, 2 doctors, 4 beds, a few equipment.
- Synthetic patient data only — no real PHI.
- **Pika MCP is never called from `er_twin/`.** uAgents only emit `out/*` files; **Claude Code CLI** (headless, `--mcp-config .mcp.json --allowedTools ...`) invokes Pika MCP as a post-processing step.

## Pika MCP — verified automation path

Pika MCP is installed at **project scope** in [.mcp.json](.mcp.json) (`https://mcp.pika.me/api/mcp`), authenticated and working. The headless Claude Code CLI **can** drive it non-interactively — the only requirement is an explicit `--allowedTools` list (in `-p` mode every MCP tool call is otherwise auto-denied; this was the original "pending approval" blocker, not OAuth). Pattern:

```bash
claude -p "<prompt>" --mcp-config .mcp.json \
  --allowedTools "mcp__pika-mcp__generate_video,mcp__pika-mcp__task_status,..." \
  --output-format json
```

A non-empty `permission_denials` array in the JSON output means a needed tool was missing from the allowlist. Long renders return `{task_id, status}` → poll `mcp__pika-mcp__task_status`. The automation scripts (`scripts/run_pika_identity_check.ps1`, `scripts/run_pika_replay.ps1`) are specified in the implementation plan (Phase 5 / P5).

## Current focus

See [STATUS.md](STATUS.md). First slice: **single-process skeleton** — one Bureau holding the Orchestrator (mailbox + Chat Protocol, reachable from ASI:One) and one stub agent, with a chat-triggered ping round-tripping in-process from the Orchestrator to the stub and back to chat.
