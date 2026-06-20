# Create an ASI:One-compatible Agent using the Chat Protocol

> Build a uAgent, put it online with a mailbox, and use the Chat Protocol so ASI:One (and other
> agents) can talk to it. **This is the framework the ER-Twin Orchestrator is built on.**

ASI:One connects to Agents that act as domain experts. This guide gets an agent online, active,
and speaking the **Chat Protocol** — the expected communication format for ASI:One.

## Prerequisites

- An ASI:One API key.
- `uagents` library installed (`pip install uagents`; `uagents-core` ships with it).
- An [Agentverse](https://agentverse.ai) account, so you can create a **mailbox** for the agent.

## The Chat Protocol

Simple string-based messages with chat states — the format ASI:One expects. Imported from
`uagents_core`:

```python
from uagents_core.contrib.protocols.chat import (
    AgentContent, ChatMessage, ChatAcknowledgement, TextContent,
    EndSessionContent, chat_protocol_spec,
)
```

Key type: **`ChatMessage(Model)`** is the wrapper for each message. It carries a list of
`content` items (`AgentContent`), most commonly `TextContent`. `EndSessionContent` signals the
session is over (no message history retained).

## The agent (`agent.py`)

A barebones expert assistant: it receives a `ChatMessage`, acknowledges it, forwards the text to
the ASI:One LLM with a system prompt, and returns the reply + `EndSessionContent`. Note the
**OpenAI client pointed at the ASI:One base URL** — the same pattern the Orchestrator uses.

```python
from datetime import datetime
from uuid import uuid4

from openai import OpenAI
from uagents import Context, Protocol, Agent
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement, ChatMessage, EndSessionContent, TextContent, chat_protocol_spec,
)

subject_matter = "the sun"  # the topic this assistant is an expert in

client = OpenAI(
    base_url='https://api.asi1.ai/v1',   # ASI:One LLM endpoint (OpenAI-compatible)
    api_key='<YOUR-API-KEY>',
)

agent = Agent(
    name="ASI-agent",
    seed="<your-agent-seedphrase>",      # deterministic address derives from the seed
    port=8001,
    mailbox=True,                        # bridges the agent <-> Agentverse <-> ASI:One
    publish_agent_details=True,
)

# Protocol compatible with the chat spec — ensures cross-agent compatibility
protocol = Protocol(spec=chat_protocol_spec)


@protocol.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    # 1. acknowledge receipt
    await ctx.send(sender, ChatAcknowledgement(
        timestamp=datetime.now(), acknowledged_msg_id=msg.msg_id))

    # 2. collect text chunks from the message content
    text = ''.join(item.text for item in msg.content if isinstance(item, TextContent))

    # 3. query the ASI:One model
    response = 'I am afraid something went wrong and I am unable to answer your question at the moment'
    try:
        r = client.chat.completions.create(
            model="asi1",
            messages=[
                {"role": "system", "content": f"You are a helpful assistant who only answers "
                 f"questions about {subject_matter}. If the user asks about any other topics, "
                 f"you should politely say that you do not know about them."},
                {"role": "user", "content": text},
            ],
            max_tokens=2048,
        )
        response = str(r.choices[0].message.content)
    except Exception:
        ctx.logger.exception('Error querying model')

    # 4. reply, and signal end of session
    await ctx.send(sender, ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[
            TextContent(type="text", text=response),
            EndSessionContent(type="end-session"),
        ],
    ))


@protocol.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass  # acks can implement read receipts; ignored here


agent.include(protocol, publish_manifest=True)

if __name__ == "__main__":
    agent.run()
```

On startup the agent prints its `agent1q...` address, an Agentverse **inspector** URL, and
registers on the **Almanac** + publishes its manifest. Successful run ends with mailbox
registration log lines.

## Enabling the mailbox

1. Open the **Agent inspector** link from the terminal output.
2. Click **connect** → select **Mailbox**.
3. Follow the modal instructions. Once done, the terminal shows
   `Successfully registered as mailbox agent in Agentverse` — the agent can now receive messages
   from any agent (and from ASI:One Chat).

## Chatting via ASI:One

With the agent running + mailbox connected, it registers in the Almanac and becomes queryable.
From the inspector → **Agent Profile** → Agentverse dashboard (edit name/handle for
discoverability) → **Chat with Agent** opens [ASI:One chat](https://asi1.ai/chat).
**The agent must be running** to chat with it. Each query arrives as an Envelope, gets processed
(you'll see `POST https://api.asi1.ai/v1/chat/completions 200 OK`), and the reply Envelope goes
back to the sender.

## Talking to it from another agent (`client.py`)

Instead of ASI:One Chat, another agent can message it directly using its address:

```python
from datetime import datetime
from uuid import uuid4
from uagents import Agent, Context, Protocol, Model
from uagents_core.contrib.protocols.chat import (
    AgentContent, ChatMessage, ChatAcknowledgement, TextContent,
)

AI_AGENT_ADDRESS = "agent1qf878gaq0jzznglu22uef96rm6pxwamwj6h0pnhgm5pzgkz4dz735hm27tf"

agent = Agent(
    name="asi-agent",
    seed="<your-client-agent-seedphrase>",
    port=8002,
    endpoint=["http://127.0.0.1:8002/submit"],
)


@agent.on_event("startup")
async def send_message(ctx: Context):
    await ctx.send(AI_AGENT_ADDRESS, ChatMessage(
        timestamp=datetime.now(),
        msg_id=uuid4(),
        content=[TextContent(type="text", text="Give me facts about the sun")],
    ))


@agent.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(f"Got an acknowledgement from {sender} for {msg.acknowledged_msg_id}")


@agent.on_message(ChatMessage)
async def handle_msg(ctx: Context, sender: str, msg: ChatMessage):
    ctx.logger.info(f"Received request from {sender} for {msg.content[0].text}")


agent.run()
```

## Relevance to this project

- The **Orchestrator** uses exactly this pattern: `mailbox=True` + `Protocol(spec=chat_protocol_spec)`
  + an OpenAI client pointed at `https://api.asi1.ai/v1`. That's its public, ASI:One-reachable surface.
- The **internal ER agents** (patient/bed/nurse/etc.) follow the same `Agent` + `@protocol.on_message`
  shape but run inside a **Bureau** (no mailbox) — see the project LLD. This guide shows the
  single-agent + mailbox case; Bureau composition is the project-specific addition.
- **Seed → deterministic address** is the project's "set agent addresses as constants at startup,
  no runtime discovery" decision in action.

## Enhance discoverability

Make the agent easier for ASI:One/users to find via the Agentverse Marketplace, agent ranking,
and README guidelines (see Agentverse docs).
