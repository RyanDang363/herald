# Fetch.ai Submission Deliverables

Submission tracker for the **UC Berkeley AI Hackathon — Fetch.ai track**. Captures the mandatory
eligibility items, the Devpost deliverables, and the canonical links/values for the ER Twin
Orchestrator. Update the `TODO`s as they're produced, then mirror the final values into
[`AGENT.md`](AGENT.md) and the Devpost submission.

> Canonical public agent: **ER Twin Orchestrator** · handle **`@er-herald`** ·
> address `agent1qty576zgxtvhugg4a4gr7pdzrhcq89g78f3kszhmd70a9ftlsamcj6a6h3w`

---

## Mandatory eligibility (Fetch.ai)

| Requirement | Status | Evidence |
|---|---|---|
| Register ≥1 agent on Agentverse | ✅ done | OrchestratorAgent registered ([profile](https://agentverse.ai/agents/details/agent1qty576zgxtvhugg4a4gr7pdzrhcq89g78f3kszhmd70a9ftlsamcj6a6h3w/profile)) |
| Implement the Agent Chat Protocol | ✅ done | Boot logs `Manifest published successfully: AgentChatProtocol` |
| Discoverable / usable through ASI:One | ✅ verified live | All 3 trigger phrases ran end-to-end via ASI:One on the live stack |
| Complete the primary workflow with **no custom frontend** | ✅ done | Entire demo runs through ASI:One chat — no UI required |
| Public GitHub repository | ✅ done | https://github.com/RyanDang363/berk-ai-hackathon |

---

## Devpost deliverables

| Deliverable | Status | Value |
|---|---|---|
| Agentverse Agent Profile URL | ✅ have | https://agentverse.ai/agents/details/agent1qty576zgxtvhugg4a4gr7pdzrhcq89g78f3kszhmd70a9ftlsamcj6a6h3w/profile |
| Public GitHub repo URL | ✅ have | https://github.com/RyanDang363/berk-ai-hackathon |
| ASI:One shared chat session URL | ⏳ **deferred** | _capture LAST — only once all agent decisions/tweaks are finalized (see below)_ |
| Short demo video | ⏳ **TODO** | _record the 3-phrase ASI:One flow + terminal logs_ |
| Problem / target user / outcome blurb | ✅ drafted | see next section |

Only the **public** agent needs a profile URL — that's the Orchestrator (`@er-herald`). The private ER
entity agents (Admissions, Triage, Patient, Bed, Nurse, Doctor, Equipment) are in-process Bureau
members and are intentionally **not** registered on Agentverse.

> **Organizer guidance — where to put the links on Devpost.** Include both the public ASI:One shared
> chat session link and the Agentverse profile link(s) in the Devpost **Project Description**. If there
> isn't a dedicated field for them, add a short **"Links"** (or **"Resources"**) section near the end
> of the submission and list them there — confirmed fine for judging/review. Example:
>
> - Public ASI:One Shared Chat Session: `[link]`
> - Agentverse Profile(s): `[link(s)]`

---

## Problem / target user / outcome (Devpost blurb)

**Problem.** Emergency rooms run in controlled chaos — every patient, nurse, doctor, bed, and piece of
equipment is a moving variable, and coordinating them in real time is hard.

**Target user.** ER operations (and, for this hackathon, the judge/operator driving the system) who
want to *act* on the ER state through plain-language commands rather than stare at a dashboard.

**Outcome.** ER Twin turns a single ASI:One chat command into **real multi-agent coordination**: a
public OrchestratorAgent on Agentverse fans out to private uAgents inside one Bureau to admit and
triage a patient, assign a specialty-appropriate bed plus nurse and doctor, autonomously resolve a
low-oxygen alert via genuine agent-to-agent messaging, and report live ER status — then export a
structured incident trace that Claude Code → Pika MCP can turn into replay media.

**One-liner.** *ER Twin satisfies Fetch.ai by turning an ASI:One chat command into real multi-agent ER
coordination through a public OrchestratorAgent on Agentverse and private uAgents running inside one
Bureau.*

---

## Verified demo (all three events, live via ASI:One)

| Phrase | Result |
|---|---|
| `A new patient arrived with chest pain` | Admitted Jordan Lee · ESI-2 · bed-1 + Nurse Chen · paged Dr. Smith (cardiology) |
| `Bed 3's patient oxygen is dropping` | Real async chain: LowSupplyAlert → locate o2-2 → dispatch Nurse Chen → swap o2-1→o2-2 at bed-3 |
| `Show me what's happening in the ER` | Read-only snapshot: active patients, bed occupancy, free/busy nurses, alerts |

---

## How to capture the remaining links

### ASI:One shared chat URL (deferred)

> **Deferred intentionally — capture this LAST.** The shared chat link is frozen evidence of a specific
> session, so it must reflect the **final** agent behavior. We're holding off until **all agent
> decisions and tweaks are finalized** (handle/profile, intent routing, the three event flows, replies,
> and any seeding/state changes). Recording it earlier risks a stale link whose responses no longer
> match the shipped agent. Once the agent is locked, capture it in one clean pass:

1. Open [asi1.ai/chat](https://asi1.ai/chat) and start a **fresh** chat.
2. Select / search the agent by handle **`@er-herald`** (or its address).
3. Run the three demo phrases in order (above) so the session shows the complete workflow.
4. Click **Share** → copy the link → paste it into the table above and into [`AGENT.md`](AGENT.md).

> Tip: rehearse on the live (`USE_MOCK=false`) stack, but you can record the judging run with
> `USE_MOCK=true` for a deterministic, dependency-free demo (same ASI:One → Orchestrator path).

### Demo video

Record: the ASI:One chat (3 phrases) → the terminal logs showing uAgent messages / state changes →
the final ASI:One responses. Optionally include a Pika replay clip.

---

## Run & verify (for judges)

```bash
# Deterministic, zero-external-dependency demo:
USE_MOCK=true uv run python -m er_twin.main

# Tests:
uv run pytest
```

See [`AGENT.md`](AGENT.md) for how to connect to the canonical agent without re-registering a copy,
and [`README.md`](README.md) for full setup + architecture.

---

## Submission checklist

- [x] Orchestrator connected to Agentverse (`@er-herald`)
- [x] Chat Protocol included and manifest published
- [x] ASI:One can chat with the Orchestrator (verified live)
- [x] Agentverse profile URL saved
- [x] Public GitHub repo
- [x] README has `uv` setup + demo commands
- [x] Agent profile README with capabilities + examples ([`AGENTVERSE_README.md`](AGENTVERSE_README.md))
- [ ] ASI:One shared chat URL saved
- [ ] Short demo video recorded
- [ ] Devpost story (problem / target user / outcome) posted
- [ ] (Optional) Pika replay artifact generated
