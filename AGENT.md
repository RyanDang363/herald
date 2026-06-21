# ER Twin Agent Connection Guide

This file is for **teammates, judges, and collaborators** who need to *use* the canonical ER Twin
agent on Agentverse / ASI:One.

**Core principle:**

> There is **one canonical public OrchestratorAgent**. Connect to it through ASI:One / Agentverse —
> do **not** re-register your own copy unless you are intentionally making a dev clone.

ASI:One reaches the agent through its Agentverse registration (Chat Protocol–compatible, mailbox
onboarded). The mailbox is tied to the *running agent identity* (its seed-derived address), and the
Agentverse profile is shareable by link — which is exactly what teammates/judges should use instead
of spinning up duplicates.

---

## Canonical public agent

| Field | Value |
|---|---|
| Agent name | **ER Twin Orchestrator** |
| Handle | **`@er-herald`** (set on the Agentverse profile) |
| Address (routing identity, **stable**) | `agent1qty576zgxtvhugg4a4gr7pdzrhcq89g78f3kszhmd70a9ftlsamcj6a6h3w` |
| Public profile README | [`AGENTVERSE_README.md`](AGENTVERSE_README.md) — paste into the Agentverse profile |
| Only public surface | **OrchestratorAgent** |
| Private helper agents | Admissions, Triage, Patient pool, Bed, Nurse, Doctor, Equipment |

**Demo trigger phrases:**

- `A new patient arrived with chest pain`
- `Bed 3's patient oxygen is dropping`
- `Show me what's happening in the ER`

> The address is the underlying cryptographic identity and never changes (it's derived from the seed).
> The handle (`@er-herald`) is the human-friendly, shareable name. Prefer the handle/profile link for
> sharing; the address is the reliable fallback until the handle is confirmed live.

---

## How teammates should use the agent

1. Open **ASI:One** (https://asi1.ai/chat).
2. Search for / select the agent by its **handle** (`@er-herald`) — or by its **address** if the handle
   isn't confirmed yet.
3. Send one of the three **demo trigger phrases** (above).
4. When available, use the **shared ASI:One chat URL** to jump straight into a working session.
5. When available, open the **Agentverse profile URL** to see the agent's profile/README.

Links (see the submission checklist at the bottom):

- Final handle: **`@er-herald`** (set on Agentverse)
- Agentverse profile URL: https://agentverse.ai/agents/details/agent1qty576zgxtvhugg4a4gr7pdzrhcq89g78f3kszhmd70a9ftlsamcj6a6h3w/profile
- ASI:One shared chat URL: **deferred** — captured LAST, only once all agent decisions/tweaks are finalized (see [`FETCHAI_DELIVERABLES.md`](FETCHAI_DELIVERABLES.md))

---

## What teammates should NOT do

- ❌ **Do not create a duplicate production Agentverse registration** of this agent on your own account.
- ❌ **Do not change the canonical seed** — the address and the connected mailbox are derived from it;
  changing it creates a *different* agent and breaks the live mailbox.
- ❌ **Do not commit `.env`** (or any seed phrase, API key, mailbox key, Redis URL, or Pika credential).
- ❌ **Do not run the canonical mailbox agent from multiple machines at the same time** unless the
  operator says so — concurrent copies of the same seed/mailbox identity cause confusing mailbox /
  routing behavior.
- ❌ **Do not register the private entity agents individually** on Agentverse — they are in-process
  Bureau members by design. Only change this if we intentionally change the architecture.

---

## Local development mode

You do **not** need ASI:One or Agentverse to develop locally.

```bash
# Deterministic, zero-external-dependency run (InMemoryStore + NoopMemory, no API calls):
USE_MOCK=true uv run python -m er_twin.main

# Run the test suite:
uv run pytest
```

- `USE_MOCK=true` is the demo-safe default — the Orchestrator resolves intents via the deterministic
  keyword lookup, no external services required.
- Local dev does **not** touch the canonical Agentverse registration.
- For **personal Agentverse experiments**, use a **different dev seed and dev handle** (override
  `AGENT_SEED` in your local `.env`) so you never collide with the canonical public agent.

---

## Canonical operator workflow

**One operator** owns the canonical public agent and is responsible for:

- Running the public Orchestrator (`USE_MOCK=false uv run python -m er_twin.main`).
- Connecting / maintaining the Agentverse **mailbox**.
- Updating the **handle / profile / README** (set in code via `Agent(handle=..., description=...)`,
  published on boot with `publish_agent_details=True`).
- Capturing the **Agentverse profile URL**.
- Capturing the **shared ASI:One chat URL**.
- Running the **final judging demo**.

Everyone else connects *through* what the operator publishes — they do not re-host the agent.

---

## Current Agentverse / Inspector caveat

- The Agentverse **Local Agent Inspector cannot onboard a full `Bureau`** directly
  (*"Agent Bureaus are not supported in this version of the Inspector"*).
- **Mailbox bootstrap (one-time):** run the **standalone** Orchestrator — same seed/address, no Bureau:
  ```bash
  uv run python -m er_twin.connect_orchestrator
  ```
  Open the Agent Inspector for that agent → **Connect → Mailbox**, wait for the success message, stop
  it (Ctrl+C). The mailbox is bound to the address, so the real Bureau runtime reuses it.
- Then run the real runtime (`uv run python -m er_twin.main`) — it reconnects to the same mailbox
  automatically (no re-registration needed for restarts, profile/handle changes, etc.).
- If the in-process mailbox approach ever fails smoke testing, use the documented **two-process
  fallback** (standalone Orchestrator process + separate entity Bureau) — see README →
  *Architecture Alternatives and Fallbacks*.

---

## Architecture reminder

```
ASI:One
  → Agentverse mailbox
    → OrchestratorAgent            (the only public surface)
      → private ER agents          (Admissions, Triage, Patient, Bed, Nurse, Doctor, Equipment)
        → shared store             (InMemoryStore | RedisStore)
          → replay files           (out/*.json, out/replay/*)
            → Pika MCP             (post-processing via Claude Code CLI — never called from er_twin/)
```

---

## Security notes

- **Never commit** seed phrases, API keys, mailbox keys, Redis secrets, or Pika credentials.
- `.env` stays **local** and is git-ignored.
- `.env.example` documents **variable names only** — no real values.
- Use a **separate dev seed** for personal Agentverse experiments so they can't collide with — or
  hijack the mailbox of — the canonical public agent.

---

## Updating this file before submission

- [x] Final handle confirmed on Agentverse (`@er-herald`)
- [x] Agentverse profile URL filled in
- [ ] ASI:One shared chat URL filled in — **deferred** until all agent decisions/tweaks are finalized
- [ ] Exact run command verified
- [ ] Exact demo phrases verified
- [ ] Known fallback path (two-process) verified / documented
