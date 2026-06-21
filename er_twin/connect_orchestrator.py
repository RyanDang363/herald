"""One-time standalone runner to create the Orchestrator's Agentverse mailbox.

The Agentverse **Local Agent Inspector** cannot onboard a `Bureau` ("Agent Bureaus are not
supported in this version of the Inspector"). So we run the SAME OrchestratorAgent —
identical seed, name, `mailbox=True`, Chat Protocol — standalone (`agent.run()`) just long
enough to do **Inspector → Connect → Mailbox**, then stop it and launch the real one-Bureau
app (`python -m er_twin.main`).

Why this works: the Agentverse mailbox is bound to the agent **address**, which is derived
deterministically from the fixed seed. Once the mailbox exists for
`agent1q...` (the Orchestrator's address), the Bureau-run Orchestrator with the same seed
reuses it — so the live demo keeps the one-process / one-Bureau architecture.

Usage (one-time, before the demo):
    uv run python -m er_twin.connect_orchestrator
Then open the Agent Inspector for this agent, Connect -> Mailbox, wait for
"Successfully registered as mailbox agent", stop this process (Ctrl+C), and run the Bureau.

This runner is for onboarding only — it does not seed state or wire the store/memory, since
no ER command is processed during the mailbox handshake.
"""

from er_twin.agents.orchestrator import orchestrator

if __name__ == "__main__":
    print(f"Standalone mailbox bootstrap for: {orchestrator.address}")
    print("Open the Agent Inspector, Connect -> Mailbox, then stop this and run er_twin.main.")
    orchestrator.run()
