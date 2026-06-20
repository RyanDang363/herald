# ASI:One Developer Platform — Overview

ASI:One is an intelligent AI platform built by **Fetch.ai**. It excels at finding the right
AI Agents to help solve everyday tasks involving language, reasoning, analysis, coding, and more.

It exposes an **OpenAI-compatible chat-completions API** (`/v1/chat/completions`), so most
OpenAI SDK patterns carry over — you just point the base URL at `https://api.asi1.ai` and use
the `asi1` model.

## Minimal request

```bash
curl -X POST https://api.asi1.ai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ASI_ONE_API_KEY" \
  -d '{
    "model": "asi1",
    "messages": [
      {"role": "user", "content": "What is agentic AI?"}
    ]
  }'
```

## Key features

- **Agentic Reasoning** — autonomously plans, executes, and adapts its approach based on
  evolving inputs and goals.
- **Natural Language Understanding** — proficient at understanding and generating human-like
  text across multiple domains.
- **Multi-Step Task Execution** — handles complex, goal-oriented tasks without constant user
  intervention.
- **Contextual Memory** — retains and uses context for longer, more coherent interactions.
- **API-Driven Integration** — embed ASI1 into applications through a simple API.
- **Web3 Native** — designed for decentralized environments and blockchain interactions.
