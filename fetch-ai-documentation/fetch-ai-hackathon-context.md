Here’s the Fetch.ai sponsor context we should keep in our heads for **ER Twin**.

## The Fetch.ai hackathon goal

The Fetch.ai challenge is **“ASI:One Agent Challenge — From Intent to Action.”** The sponsor wants projects where a user can ask for something in ASI:One, an agent understands the intent, and the system takes meaningful action — not just chatbot text or a thin API wrapper. The official “What to Build” section says the project should solve a real-world problem, perform multi-step planning/orchestration, use tools/APIs/data/other agents to produce an executable outcome, be registered on Agentverse, be usable through ASI:One, and demo the core use case directly inside an ASI:One conversation. ([Fetch.ai][1])

For us, that means:

```text
User in ASI:One:
  "Bed 3's patient oxygen is dropping"

OrchestratorAgent:
  understands the ER intent
  coordinates EquipmentAgent + NurseAgent + state updates
  returns a useful operational response
  emits a trace for replay
```

That is a strong fit because ER Twin is not “chat about hospitals.” It is an **agentic ER coordination workflow**.

## Mandatory Fetch.ai requirements

To be prize-eligible, the hackathon page lists these mandatory requirements:

```text
1. Register at least one agent on Agentverse.
2. Implement the Agent Chat Protocol.
3. Make the agent discoverable and directly usable through ASI:One.
4. Demonstrate meaningful tool execution or agent-to-agent orchestration.
5. Complete the primary user workflow without requiring a custom frontend.
6. Submit a public GitHub repo with run/test instructions.
```

Those are stated directly in the hackpack. ([Fetch.ai][1])

For our project, the interpretation is:

| Requirement                 | ER Twin implementation                                    |
| --------------------------- | --------------------------------------------------------- |
| Register at least one agent | Register **OrchestratorAgent**                            |
| Chat Protocol               | Orchestrator includes `Protocol(spec=chat_protocol_spec)` |
| Usable through ASI:One      | ASI:One talks to Orchestrator via Agentverse mailbox      |
| Meaningful orchestration    | Orchestrator coordinates ER entity agents                 |
| No custom frontend required | Demo works fully through ASI:One chat                     |
| GitHub repo                 | Public repo with setup, run, demo commands                |

Important: **“at least one agent”** does not mean every ER entity agent must be registered publicly. Our design registers only the Orchestrator, and the private ER agents run inside the Bureau. That matches our plan and the workshop guidance that one user-facing agent can internally call non-user-facing agents. 

## Judging criteria

The official judging criteria are:

```text
Functionality & Technical Implementation — 25%
Use of Fetch.ai Technology — 25%
Innovation & Creativity — 20%
Real-World Impact & Usefulness — 20%
User Experience & Presentation — 10%
```

The Fetch.ai section specifically asks whether the agent is properly registered on Agentverse, usable through ASI:One via Chat Protocol, and whether the Fetch integration is central rather than bolted on. ([Fetch.ai][1])

So our judging strategy should be:

```text
Functionality:
  Three scripted ER events work reliably.

Fetch.ai tech:
  ASI:One → Agentverse → Orchestrator → private uAgents.

Innovation:
  Hospital ER digital twin + Pika replay layer.

Impact:
  Operations visibility, incident response, care coordination.

Presentation:
  One clean ASI:One chat session + replay artifact.
```

## Bonus points

Fetch.ai says projects may get additional consideration for:

```text
- Effective multi-agent collaboration
- Payment Protocol + credible monetization model
- Strong reliability/error handling/recovery
- Creative use of real-time data or external services
- Agent could realistically continue operating after hackathon
```

([Fetch.ai][1])

For ER Twin, the best bonus alignment is:

| Bonus                     | Our move                                                           |
| ------------------------- | ------------------------------------------------------------------ |
| Multi-agent collaboration | Orchestrator + Admissions/Triage/Bed/Nurse/Doctor/Equipment agents |
| Reliability               | `USE_MOCK=true`, deterministic triggers, graceful fallbacks        |
| External service          | Pika MCP replay generation after event trace                       |
| Post-hackathon viability  | Redis-backed ER state/event log later                              |
| Payment Protocol          | Optional/cuttable; do not prioritize unless everything else works  |

I would **not** prioritize Payment Protocol now. It is impressive, but it adds complexity. Our stronger path is reliable multi-agent coordination plus replay.

## Required deliverables

The hackpack says Devpost should include:

```text
- Public ASI:One shared chat session URL showing the complete workflow
- Agentverse Agent Profile URL(s) for each submitted agent
- Public GitHub repository URL
- Short demo video
- Brief description of the problem, target user, and outcome produced by the agent
```

([Fetch.ai][1])

For us, that means the final submission should have:

```text
1. ASI:One shared chat link
   Shows the ER Twin commands working.

2. Agentverse profile URL
   At minimum: OrchestratorAgent profile.

3. GitHub repo
   Clear README with uv setup and demo commands.

4. Short demo video
   Show ASI:One chat, logs/state, and Pika replay output.

5. Devpost story
   Problem: ER overload / coordination visibility.
   User: charge nurse / ER operations lead.
   Outcome: coordinated intake, oxygen response, live summary, replay artifact.
```

## What the ASI-compatible agent must do

The official ASI-compatible uAgent example creates a local agent with:

```python
Agent(
    name="ASI-agent",
    seed="<your-agent-seedphrase>",
    port=8001,
    mailbox=True,
    publish_agent_details=True,
)
```

and constructs the Chat Protocol with:

```python
Protocol(spec=chat_protocol_spec)
```

The handler receives `ChatMessage`, sends `ChatAcknowledgement`, processes `TextContent`, and sends back a `ChatMessage`. ([uAgents][2])

For ER Twin, that means our **OrchestratorAgent** needs:

```text
mailbox=True
publish_agent_details=True
Protocol(spec=chat_protocol_spec)
ChatMessage handler
ChatAcknowledgement response
TextContent parser
USE_MOCK intent resolver
ctx.send(...) to private agents
final ChatMessage reply to user
```

Your project plan already captures this: Phase 1 is the mandatory Fetch judging path, where ASI:One reaches the Agentverse mailbox Orchestrator, the Orchestrator uses Chat Protocol, and `USE_MOCK` provides deterministic trigger routing. 

## Agentverse, ASI:One, and private agents

The official Agentverse docs say registering a local uAgent into Agentverse and enabling Agent Chat Protocol makes it discoverable and accessible through ASI:One. They also say the agent must be ACP-compatible and reachable through an endpoint for Agentverse onboarding. ([Agentverse Documentation][3])

But private agents inside a Bureau do **not** need to be individually registered for our design. The uAgents Bureau docs say a Bureau lets multiple agents operate together in a shared environment, handling communication/task coordination; their example shows `agent_a` sending directly to `agent_b.address`, and `agent_b` replying, all inside the Bureau. ([uAgents][4])

So our architecture is defensible:

```text
Public Fetch surface:
  OrchestratorAgent
    - Agentverse profile
    - mailbox=True
    - Chat Protocol
    - ASI:One reachable

Private Fetch system:
  AdmissionsAgent
  TriageAgent
  PatientAgents
  BedAgents
  NurseAgents
  DoctorAgents
  EquipmentAgents
    - Bureau-local
    - uAgent addresses
    - message handlers
    - no public Agentverse profile required
```

Your implementation plan explicitly locks this: only the Orchestrator is registered; ASI:One talks to nothing else; Orchestrator and private entity agents run in one Bureau/process. 

## What the Fetch workshop taught us

From the workshop transcript you gave me:

```text
- Chat Protocol is needed for ASI:One discovery/reachability.
- A local mailbox agent must be connected through Agent Inspector → Connect → Mailbox.
- An agent README/profile helps discoverability.
- One user-facing agent can internally call multiple non-user-facing agents.
- Multi-agent systems are impressive for judges.
```

The transcript specifically says Chat Protocol is important/mandatory for the hackathon because without it, an agent may not be reachable from ASI:One.  It also says one user-facing agent can internally call multiple non-user-facing agents, with the quickstarter as the example. 

So our public/private split is not a hack. It is the right story:

> “ASI:One talks to one public OrchestratorAgent. The Orchestrator coordinates a private hospital of uAgents.”

## What the Fetch quickstarter shows

The Fetch hackathon quickstarter is a multi-agent system with an orchestrator that routes messages to specialized agents. Its README says each agent runs with its own seed, and the setup involves starting the orchestrator and helper agents, connecting agents through Agent Inspector, selecting Mailbox, and then chatting with the Orchestrator profile. ([GitHub][5])

Our project differs in one implementation detail:

```text
Quickstarter:
  multiple processes / terminals

ER Twin:
  one process / one Bureau
```

That is okay because the Bureau docs support multiple agents in one shared runtime, and our local spike proved `mailbox=True` Orchestrator inside Bureau works on `uagents==0.25.2`. The two-process quickstarter remains a fallback pattern if ASI:One smoke testing fails.

## Lessons from AgenticHire example

The Devpost example you linked, **AgenticHire**, won Best Use of Fetch.ai at DiamondHacks 2026. Their pitch was very Fetch-aligned: a user types one message in ASI:One, five Fetch.ai agents coordinate a recruiting workflow, and the system performs real actions like ranking candidates and sending outreach. ([Devpost - The home for hackathons][6])

Important lessons from AgenticHire:

```text
1. Make the ASI:One interaction the front door.
2. Make the workflow visibly multi-agent.
3. Give agents named roles.
4. Produce an actual outcome, not just text.
5. Explain async coordination/session management.
6. Show reliability/fallbacks.
```

AgenticHire described five agents: Orchestrator, Recruiter, Talent Scout, Ranker, and Outreach Agent. It also highlighted that session management across asynchronous agents was a major challenge. ([Devpost - The home for hackathons][6])

For ER Twin, the equivalent is:

```text
OrchestratorAgent
AdmissionsAgent
TriageAgent
PatientAgent pool
BedAgent
NurseAgent
DoctorAgent
EquipmentAgent
```

And the actual outcome is:

```text
patient admitted
bed assigned
nurse/doctor assigned
oxygen unit replaced
ER status summarized
incident replay generated
```

AgenticHire used Payment Protocol and all agents registered on Agentverse, but that is **not required** for us. Their approach is an example, not a rule. The current Berkeley requirement says at least one registered agent, and our workshop materials support one user-facing orchestrator with internal agents. ([Fetch.ai][1]) 

## What ER Twin needs to implement to satisfy Fetch.ai

### Must-have implementation

```text
1. One public OrchestratorAgent
   - mailbox=True
   - publish_agent_details=True
   - Chat Protocol
   - Agentverse-connected
   - callable from ASI:One

2. ASI:One chat workflow
   - user sends one of the demo phrases
   - Orchestrator acknowledges
   - Orchestrator resolves intent
   - Orchestrator coordinates work
   - Orchestrator replies with outcome

3. Meaningful multi-agent coordination
   - intake event or oxygen event must show actual coordination
   - ideally oxygen event uses real async uAgent messages

4. Deterministic demo
   - USE_MOCK=true
   - no external LLM dependency required during judging
   - fixed trigger phrases

5. Clear state changes
   - patient/bed/nurse/doctor/equipment state updates
   - summaries derived from store

6. Repo instructions
   - uv setup
   - run command
   - test command
   - demo phrases
```

### Should-have implementation

```text
7. Incident trace / replay files
   - out/incident_replay_brief.json
   - out/pika_prompt.md

8. Pika MCP replay
   - not Fetch-required, but strong for cross-sponsor story

9. Agentverse profile polish
   - good name
   - useful README
   - example queries
   - keywords
```

### Nice-to-have only

```text
10. Payment Protocol
11. RedisStore
12. Dashboard
13. Frontend
14. PharmacyAgent
15. fal.ai fallback
```

## The three Fetch demo commands

Use these as the ASI:One chat workflow:

```text
"A new patient arrived with chest pain"
"Bed 3's patient oxygen is dropping"
"Show me what's happening in the ER"
```

Those map directly to the sponsor’s “intent to action” goal:

| Chat phrase                 | Intent           | Action                                       |
| --------------------------- | ---------------- | -------------------------------------------- |
| New patient with chest pain | Patient intake   | create patient, triage, assign bed/staff     |
| Bed 3 oxygen dropping       | Low oxygen alert | equipment alert, locate unit, dispatch nurse |
| Show ER status              | Summary          | read state and summarize operations          |

## Strongest Fetch.ai judging story

Say this in the demo:

> “We built an ER digital twin where ASI:One talks to one public Fetch.ai OrchestratorAgent. That Orchestrator coordinates private uAgents representing admissions, triage, patients, beds, nurses, doctors, and equipment. The agents update shared ER state and produce an operational result. This is more than a chatbot: the user intent triggers real multi-agent coordination.”

Then show:

```text
1. Agentverse profile for OrchestratorAgent
2. ASI:One chat command
3. terminal logs showing uAgent messages
4. final ASI:One response
5. state summary / event trace
6. optional Pika replay media
```

## Agentverse profile content

Your Orchestrator profile should make discoverability obvious:

```text
Name:
  ER Twin Orchestrator

Short description:
  Coordinates a simulated emergency room using Fetch.ai uAgents.

Capabilities:
  - Admit a synthetic patient from an ASI:One chat request
  - Triage acuity and assign an appropriate bed
  - Coordinate nurses, doctors, beds, and oxygen equipment
  - Respond to low-oxygen alerts
  - Summarize current ER status
  - Export incident traces for replay media

Example queries:
  - A new patient arrived with chest pain
  - Bed 3's patient oxygen is dropping
  - Show me what's happening in the ER

Important note:
  Uses synthetic demo data only. No real patient health information.
```

## Final checklist before submission

```text
Fetch.ai eligibility:
[ ] Orchestrator connected to Agentverse
[ ] Chat Protocol included and manifest published
[ ] ASI:One can chat with Orchestrator
[ ] ASI:One shared chat URL saved
[ ] Agentverse profile URL saved
[ ] GitHub repo public
[ ] README has uv setup + demo commands
[ ] Short demo video recorded

Technical judging:
[ ] At least one end-to-end ER event works
[ ] Private uAgents coordinate or are clearly represented
[ ] Logs show agent-to-agent messages or agent-owned state changes
[ ] Graceful fallback / deterministic USE_MOCK works
[ ] No custom frontend required

Polish:
[ ] Agent README/profile has capabilities + examples
[ ] Demo script uses exact phrases
[ ] Pika replay artifact generated if possible
[ ] Devpost story clearly explains problem, target user, and outcome
```

## One-sentence target

> **ER Twin satisfies Fetch.ai by turning an ASI:One chat command into real multi-agent ER coordination through a public OrchestratorAgent on Agentverse and private uAgents running inside one Bureau.**

[1]: https://www.fetch.ai/events/hackathons/uc-berkeley-ai-hackathon-2026/hackpack "UC Berkeley AI Hackathon 2026"
[2]: https://uagents.fetch.ai/docs/examples/asi-1 "Create an ASI:One compatible Agent using the chatprotocol docs"
[3]: https://docs.agentverse.ai/documentation/launch-agents/external-agents/u-agents "uAgents | Agentverse Documentation"
[4]: https://uagents.fetch.ai/docs/guides/bureau "Bureau docs"
[5]: https://github.com/fetchai/innovation-lab-examples/tree/main/fetch-hackathon-quickstarter "innovation-lab-examples/fetch-hackathon-quickstarter at main · fetchai/innovation-lab-examples · GitHub"
[6]: https://devpost.com/software/agentichire-2xyk0z "AgenticHire | Devpost"
