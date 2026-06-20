# Redis Context Retriever

```json metadata
{
  "title": "Redis Context Retriever",
  "description": "Expose tools to Agents to query your Redis databases.",
  "categories": ["docs","develop","ai"],
  "tableOfContents": {"sections":[{"id":"overview","title":"Overview"},{"id":"get-started-with-redis-context-retriever","title":"Get started with Redis Context Retriever"}]}

,
  "codeExamples": []
}
```
Redis Context Retriever helps teams expose operational context to AI agents through schema-first retrieval. It models the entities, fields, keys, and relationships that matter to an agent workflow, then presents that context through a governed tool surface the agent can call at runtime. Context Retriever helps an AI Agent understand what business objects exist, how they connect, and which paths are safe to use.

## Overview

Production agents fail not because the model is wrong, but because the context layer breaks. Enterprise data can be fragmented across multiple different databases, and can be disorganized. Teams try to patch this with text-to-SQL, OpenAPI-to-MCP wrappers, or hand-built tools — which works for demos but creates tool zoo sprawl, SQL risk, and agents that can't reliably choose the right path in production. Redis Context Retriever gives teams a governed, schema-first surface agents can traverse safely.

When you set up Redis Context Retriever, you model the objects that matter to your agent workflow and connect the relationships between them. You can do this either through the UI, using the [Context Surfaces Python Client](https://pypi.org/project/redis-context-retriever/), or the `ctxctl` CLI (available when you install the python client). Context Retriever will use those relationships to automatically create and deploy retrieval tools from your entity model.  

When an agent needs context during execution, it calls the MCP tools Context Retriever exposes. Instead of guessing which tool to use, or generating SQL, the agent follows the defined entity paths and gets back structured, live, operational context. 

## Get started with Redis Context Retriever

Get started with Redis Context Retriever on Redis Cloud or join the private preview for Redis Software.

**Redis Cloud:**

To set up a Redis Context Retriever on Redis Cloud, you need a database on Redis Cloud that already has relevant data. If you use a relational database, use [Redis Data Integration (RDI)](https://redis.io/docs/latest/operate/rc/rdi) to ingest data into a Redis Cloud database.

When you have a database, [Create a context retriever service](https://redis.io/docs/latest/operate/rc/context-engine/context-retriever/create-service) for your database on Redis Cloud.

After you set up Context Retriever, you can [view your service](https://redis.io/docs/latest/operate/rc/context-engine/context-retriever/view-service). See the [Context Surfaces Python Client](https://pypi.org/project/context-surfaces/) for more information on how to call your tools.

**Redis Software (private preview):**

Contact your Redis representative or [contact sales](https://redis.com/contact-sales/) to join the private preview on Redis Software.




