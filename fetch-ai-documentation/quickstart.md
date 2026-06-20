# ASI:One Developer Quickstart

Get up and running with ASI:One in minutes.

## Prerequisites

- An ASI:One API key
- Basic knowledge of HTTP requests
- Your preferred language (Python, JavaScript, or cURL)

## Step 1 — Get your API key

1. Sign up at the ASI:One Platform.
2. Navigate to the **Developer** section.
3. Click **Create New**.
4. Name your `api_key` and save it somewhere safe.

> Store it as an env var (e.g. `ASI_ONE_API_KEY`) — do **not** commit it. `.env` is gitignored
> in this repo.

## Step 2 — Make your first request

```bash
curl https://api.asi1.ai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ASI_ONE_API_KEY" \
  -d '{
    "model": "asi1",
    "messages": [
      {"role": "user", "content": "Hello! How can you help me today?"}
    ]
  }'
```

## Step 3 — Understanding the response

```json
{
    "id": "ec3e76554baa4ebb838173e7f32fdb94",
    "choices": [{
        "finish_reason": "stop",
        "index": 0,
        "logprobs": null,
        "message": {
            "content": "Hey there! 👋 ...",
            "refusal": null,
            "role": "assistant",
            "annotations": null,
            "audio": null,
            "function_call": null,
            "tool_calls": null,
            "reasoning_content": null
        },
        "matched_stop": 151336
    }],
    "created": 1768409272,
    "model": "asi1",
    "object": "chat.completion",
    "service_tier": null,
    "system_fingerprint": null,
    "usage": {
        "completion_tokens": 149,
        "prompt_tokens": 2105,
        "total_tokens": 2254,
        "completion_tokens_details": null,
        "prompt_tokens_details": null,
        "reasoning_tokens": 0
    },
    "metadata": {
        "weight_version": "default"
    }
}
```

### Fields you usually read

- `choices[0].message.content` — the assistant's reply text.
- `usage` — token accounting for cost/limits.

### Agent-specific fields

- `executable_data` — where an agentic model returns tool calls or agent manifests (empty
  unless discovery was requested).
- `intermediate_steps` — debugging breadcrumbs for multi-step plans.
- `thought` — a lightweight reasoning trace; often just newlines when no explicit
  chain-of-thought was needed.

## Next steps

- Learn about **function calling** (not yet included here — see gaps in [CLAUDE.md](CLAUDE.md)).
- Read the **full API reference** (not yet included here).
