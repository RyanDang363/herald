# Fetch.ai / ASI:One Documentation — Index for Claude Code

Reference material for using **Fetch.ai's ASI:One** platform (a sponsored hackathon tool) in
this project. Read it to answer "how do I call ASI:One," not to learn what we're building.

## Files

- [asi-one-overview.md](asi-one-overview.md) — what ASI:One is, key features, minimal request.
  **Key fact: it's an OpenAI-compatible `/v1/chat/completions` API** — point an OpenAI SDK at
  `https://api.asi1.ai` with model `asi1`.
- [quickstart.md](quickstart.md) — get an API key, first request, full response anatomy
  (incl. agent-specific fields: `executable_data`, `intermediate_steps`, `thought`).
- [models.md](models.md) — the three-model family (`asi1` / `asi1-ultra` / `asi1-mini`),
  specs table, shared capabilities, use-case-to-model mapping, trust & safety.
- [tool-calling.md](tool-calling.md) — full tool/function-calling guide: schema, end-to-end
  execution cycle, tool-result rules (ID/order/stringify/error traps), `tool_choice`,
  `parallel_tool_calls`, `strict` mode.

## Fast facts

- Base URL: `https://api.asi1.ai`  ·  Endpoints: `POST /v1/chat/completions` and `/v1/responses`
- **Models:** `asi1` (adaptive default) · `asi1-ultra` (deepest reasoning, up to 500 tool
  calls/turn) · `asi1-mini` (fastest/cheapest). Same key for all; switch via the `model` field.
- All models: **200K context window**, streaming supported, full OpenAI SDK compatibility.
- Auth: `Authorization: Bearer $ASI_ONE_API_KEY`
- Reply text lives at `choices[0].message.content`; cost at `usage`.
- Agentic reasoning orchestrates agents from the **Agentverse marketplace**.
- Keep the key in an env var — `.env` is gitignored.

## Gaps (NOT covered by the docs we have)

These are still missing and may matter depending on what we build:

1. **Agent discovery** — `executable_data` and Agentverse orchestration are described, but how
   to *request* discovery / invoke discovered agents isn't shown.
2. **Responses API** — `/v1/responses` endpoint is listed but not documented (no request/response shape).
3. **Streaming format** — confirmed supported, but the SSE/chunk shape isn't documented here.
4. **uAgents / Agentverse (building agents)** — Fetch.ai's framework for building & registering
   autonomous agents. ASI:One can *orchestrate* Agentverse agents, but creating them is a
   separate topic. If our project builds agents rather than just calling the chat API, pull
   those docs in.

_Resolved: tool calling / function schema (→ [tool-calling.md](tool-calling.md))._

> If we need any of the above, grab the relevant page from https://docs.asi1.ai /
> Fetch.ai docs and drop it in here.
