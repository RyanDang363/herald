# ASI:One Models

ASI:One offers a family of **three models** that share the same API surface and capability
set. Same API key works across all three — switch by changing the `model` field.

| | asi1 | asi1-ultra | asi1-mini |
|---|---|---|---|
| **Position** | Adaptive default | Deepest reasoning | Fastest response |
| **Best for** | General agent workflows, chat, tool calling, mixed | Long agentic runs, deep research, code audits, orchestration | Real-time chat, classification, autocomplete, voice |
| **Context window** | 200,000 tokens | 200,000 tokens | 200,000 tokens |
| **Max tool calls / turn** | Standard | Up to 500 | Standard |
| **Streaming** | Supported | Supported | Supported |
| **OpenAI compatibility** | Full SDK | Full SDK | Full SDK |
| **Chat Completions API** | `/v1/chat/completions` | `/v1/chat/completions` | `/v1/chat/completions` |
| **Responses API** | `/v1/responses` | `/v1/responses` | `/v1/responses` |
| **Rate limits** | See API dashboard | See API dashboard | See API dashboard |

**Pick:** `asi1` to start (adapts to the request) · `asi1-ultra` for max reasoning depth and
the largest tool budget · `asi1-mini` for fastest/cheapest.

## Shared capabilities

All three support the same capability set; they differ only in reasoning depth, tool budget,
response size, and latency.

- **Agentic Reasoning** — discovers and orchestrates AI agents from the **Agentverse
  marketplace** (booking, research, scheduling, etc.). `asi1-ultra` sustains the longest runs.
- **Extended Reasoning** — multi-step analysis with intermediate validation; `asi1-ultra`
  goes deepest (code review, contract analysis, research synthesis, planning).
- **Fast Inference** — low-latency responses; `asi1-mini` is purpose-built for this.
- **Tool Calling** — define functions, the model decides when/how to call them. `asi1-ultra`
  supports up to **500 tool calls per turn**.
- **Visualization** — generates charts/graphs from datasets.
- **Web3 Native** — understands smart contracts, tokenomics, on-chain interactions.

## Use cases by model

| Use case | Model | Why |
|---|---|---|
| Customer support | asi1 | Adapts between fast triage and longer escalation |
| Research & analysis | asi1-ultra | Multi-hop retrieval + synthesis with citations |
| Code generation | asi1 | Routine coding at the right depth |
| Code review & audit | asi1-ultra | Deepest reasoning for subtle issues |
| Content creation | asi1 | General drafting/editing |
| Real-time chat | asi1-mini | Low latency, short turns |
| Classification & routing | asi1-mini | Cheap, fast, deterministic |
| Voice assistants | asi1-mini | Speed-critical, short outputs |
| Long-running agent tasks | asi1-ultra | Largest tool budget, deepest plans |
| Data visualization | asi1 | Generates charts/visual explanations |
| Web3 applications | asi1 | Smart contract analysis with adaptive depth |

## Trust & safety

- **Transparent Reasoning** — reasoning traces expose the thought process.
- **Reduced Hallucination** — confidence thresholds and cross-checks.
- **Safety Filters** — built-in guardrails screen harmful content.
- **Audit Support** — hashed reasoning steps for compliance logging.
