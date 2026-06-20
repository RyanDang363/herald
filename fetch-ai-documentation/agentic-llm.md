# Agentic LLM — ASI:One + Agentverse Marketplace

> Build applications where the `asi1` model autonomously discovers and calls agents from the
> [Agentverse marketplace](https://agentverse.ai/) for complex workflows.

**Scope note (read first):** this is about ASI:One *consuming* ready-made agents from the
Agentverse **marketplace** — you send natural language, the model finds and orchestrates a
suitable public agent (e.g. an image-gen agent). It is **NOT** about building your own uAgents
with the `uagents` library / Bureau. For this project's architecture (own uAgents in a local
Bureau, one Orchestrator on a mailbox), this pattern is mostly tangential — but the
**streaming** and **session-management** mechanics below are directly reusable for the
Orchestrator's chat surface.

---

## How it works

The agentic `asi1` model handles agent selection, orchestration, and execution planning
autonomously. You don't define tools — you describe the task and supply a session id; the model
discovers the relevant marketplace agent and runs it.

Key features: autonomous agent discovery · session persistence · async processing for
long-running agent workflows · streaming.

## The critical header: `x-session-id`

Agentic calls require session persistence to keep context across agent interactions. **Include
`x-session-id` on every request** (use a UUID; in production store the conversation→session
mapping in Redis or a DB).

```python
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "x-session-id": session_id,   # UUID per conversation
    "Content-Type": "application/json",
}
payload = {"model": "asi1", "messages": messages, "stream": stream}
resp = requests.post("https://api.asi1.ai/v1/chat/completions", headers=headers, json=payload)
```

A request is just natural language, e.g.
`{"role": "user", "content": "use Hi-dream model to generate image of a monkey on a mountain"}`.
The model returns a direct result (e.g. an image URL) once the marketplace agent completes.

## Streaming format (SSE) — reusable everywhere

This is the concrete streaming shape (closes the earlier "streaming format undocumented" gap).
Server-sent events, `data: ` prefix, `[DONE]` sentinel, token text at
`choices[0].delta.content`:

```python
with requests.post(ENDPOINT, headers=headers, json=payload, timeout=90, stream=True) as resp:
    resp.raise_for_status()
    full_text = ""
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        line = line[len("data: "):]
        if line == "[DONE]":
            break
        chunk = json.loads(line)
        choices = chunk.get("choices")
        if choices and "content" in choices[0].get("delta", {}):
            full_text += choices[0]["delta"]["content"]
    return full_text
```

(JS uses the same SSE shape: read the body stream, split on `\n`, strip `data: `, stop on
`[DONE]`, read `parsed.choices[0].delta.content`.)

## Asynchronous / deferred agent responses

When a marketplace agent needs time, the model may return a deferred reply (e.g. the literal
`"I've sent the message"`). Poll by re-asking "Any update?" on the same session until the reply
text changes:

```python
def poll_for_async_reply(conv_id, history, *, wait_sec=5, max_attempts=24):  # ~2 min
    for attempt in range(max_attempts):
        time.sleep(wait_sec)
        latest = ask(conv_id, history + [{"role": "user", "content": "Any update?"}], stream=False)
        if latest and latest.strip() != history[-1]["content"].strip():
            return latest
    return None
```

## Best practices

- **Session:** UUID session ids; store the mapping in Redis/DB; send `x-session-id` every request.
- **Errors:** timeouts on long agent tasks; exponential backoff on network failures; validate
  responses before use.
- **Performance:** stream for UX; async-poll for deferred responses.
- **Coordination:** be specific in requests to aid discovery; allow time for multi-agent flows.
