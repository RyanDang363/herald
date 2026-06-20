# Tool Calling with ASI:One

> Extend ASI:One models with custom functions and real-world actions through intelligent tool selection.

Tool calling lets models invoke external functions with the right parameters — integrating
APIs, tools, or your own code to retrieve live data, perform tasks, or trigger actions. The
flow: you define tools → the model decides to call them → you execute and return results → the
model incorporates the output into its final reply.

## Basic example

```python
import requests
import json

API_KEY = "your_api_key"
BASE_URL = "https://api.asi1.ai/v1"
headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

get_weather_tool = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current temperature for a given location (latitude and longitude).",
        "parameters": {
            "type": "object",
            "properties": {
                "latitude": {"type": "number"},
                "longitude": {"type": "number"}
            },
            "required": ["latitude", "longitude"]
        }
    }
}

initial_message = [
    {"role": "system", "content": "You are a weather assistant. When a user asks for the weather in a location, use the get_weather tool with the appropriate latitude and longitude for that location."},
    {"role": "user", "content": "What's the current weather like in Indore right now?"}
]

payload = {
    "model": "asi1",
    "messages": initial_message,
    "tools": [get_weather_tool],
    "temperature": 0.7,
    "max_tokens": 1024
}

response = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload)
```

### Example response (model decides to call the tool)

`finish_reason` is `"tool_calls"`, and `message.tool_calls` carries the call:

```json
{
    "choices": [{
        "finish_reason": "tool_calls",
        "message": {
            "content": "I'll get the current weather information for Indore, India for you.",
            "role": "assistant",
            "tool_calls": [{
                "id": "call_13f125faf3cc422e81b10621",
                "function": {
                    "arguments": "{\"latitude\": 22.7196, \"longitude\": 75.8577}",
                    "name": "get_weather"
                },
                "type": "function",
                "index": -1
            }]
        }
    }],
    "model": "asi1",
    "object": "chat.completion",
    "usage": {"completion_tokens": 40, "prompt_tokens": 2210, "total_tokens": 2250}
}
```

### Sample tool implementations (your code)

```python
def get_weather(latitude, longitude):
    response = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=temperature_2m,wind_speed_10m&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m")
    data = response.json()
    return data['current']['temperature_2m']
```

```javascript
async function getWeather(latitude, longitude) {
  const response = await fetch(
    `https://api.open-meteo.com/v1/forecast?latitude=${latitude}&longitude=${longitude}&current=temperature_2m,wind_speed_10m&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m`
  );
  const data = await response.json();
  return data.current.temperature_2m;
}
```

## Complete tool execution cycle

**Step 1 — Initial request with tools** (see basic example above).

**Step 2 — Parse tool calls from response:**

```python
first_response.raise_for_status()
first_response_json = first_response.json()

tool_calls = first_response_json["choices"][0]["message"].get("tool_calls", [])
messages_history = [
    initial_message,
    first_response_json["choices"][0]["message"]
]
```

**Step 3 — Execute tools and format results:**

```python
for tool_call in tool_calls:
    function_name = tool_call["function"]["name"]
    arguments = json.loads(tool_call["function"]["arguments"])

    if function_name == "get_weather":
        temperature = get_weather(arguments["latitude"], arguments["longitude"])
        result = {"temperature_celsius": temperature,
                  "location": f"lat: {arguments['latitude']}, lon: {arguments['longitude']}"}
    else:
        result = {"error": f"Unknown tool: {function_name}"}

    messages_history.append({
        "role": "tool",
        "tool_call_id": tool_call["id"],
        "content": json.dumps(result)
    })
```

**Step 4 — Send results back to the model:**

```python
final_payload = {"model": "asi1", "messages": messages_history, "temperature": 0.7, "max_tokens": 1024}
final_response = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=final_payload)
```

**Step 5 — Receive final answer:**

```python
final_response_json = final_response.json()
print(final_response_json["choices"][0]["message"]["content"])
```

## Tool result handling — critical rules

These are the common-error traps. Get them wrong and the request fails:

1. **Preserve tool call IDs** — send results back with the **exact** `tool_call_id` from the
   model's response. Made-up IDs cause an error.
2. **Message history order** must be exactly: original user message → assistant message with
   `tool_calls` (content null/empty) → tool result message(s), one per `tool_call`, each keyed
   by `tool_call_id`.
3. **JSON-stringify content** — tool results must be `json.dumps(...)` in the `content` field.
   Raw objects cause an error.
4. **Errors** — if a tool fails, still return a `role: "tool"` message with the original
   `tool_call_id` and a JSON-stringified error payload (don't drop the message).

## Tool definition schema

Each tool is a function object passed in the `tools` array. Key fields:

- **`name`** (string) — unique, descriptive id (`get_weather_forecast`, `send_email`). Use
  underscores or camelCase; no spaces or special chars.
- **`description`** (string) — what the tool does and when to use it. Clearer = better calls.
- **`parameters`** (object):
  - **`type`** — usually `"object"`.
  - **`properties`** — each input param: `type` (`string`/`integer`/`boolean`/`array`/…),
    `description`, optional `enum` (allowed values).
  - **`required`** — array of param names that must be supplied.

```json
{
  "type": "function",
  "function": {
    "name": "get_weather",
    "description": "Retrieves current weather for the given location.",
    "parameters": {
      "type": "object",
      "properties": {
        "location": {"type": "string", "description": "City and country e.g. Bogotá, Colombia"},
        "units": {"type": "string", "enum": ["celsius", "fahrenheit"], "description": "Units the temperature will be returned in."}
      },
      "required": ["location", "units"],
      "additionalProperties": false
    },
    "strict": true
  }
}
```

## Additional configuration

### `tool_choice`

- `"auto"` (default) — model may call zero, one, or multiple functions.
- `"required"` — model must call at least one function.
- Forced function — `{"type": "function", "function": {"name": "get_weather"}}`.
- `"none"` — model calls no functions.

### `parallel_tool_calls`

Default true (model may call multiple functions per turn). Set `false` to restrict to at most
one per turn. **Note:** if parallel calls are enabled, strict mode may be disabled for them.

### `strict` mode (recommended)

`strict: true` forces the model to follow the schema exactly. Requirements:

1. `additionalProperties` must be `false` for each object in `parameters`.
2. All fields in `properties` must be listed in `required`.

(For an optional field under strict mode, make it nullable, e.g. `"type": ["string", "null"]`,
and keep it in `required`.)
