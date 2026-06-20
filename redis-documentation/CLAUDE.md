# Redis Documentation — Index for Claude Code

This folder is reference material for using Redis (a sponsored hackathon tool) in this
project. It is **scraped docs, not project docs** — read it to answer "how does Redis do X,"
not to learn what we're building.

## Reading rules (important for context economy)

- **`redis-8-8-commands.md` is a 6,472-line / ~50K-token full command dump. GREP IT, DO NOT
  READ IT WHOLE.** Reading it entirely burns ~25% of the context window. Search for the
  specific command (e.g. `grep -n "JSON.SET" redis-8-8-commands.md`) and read only that
  block. Same spirit for `client-tools/cli.md` (978 lines) — grep for the flag/subcommand.
- For everything else, read the whole file — they're right-sized.
- Several files start with a `json metadata` block and end with "Continue learning with
  Redis University" filler. That's scrape cruft — skip it.

## Start here (most relevant for an AI hackathon project)

These four are the core. If the project does anything with LLMs/agents, read these first:

- [redis-iris/redis-agent-memory.md](redis-iris/redis-agent-memory.md) — short-term +
  long-term agent memory as a service. **Directly relevant to cross-session Claude Code work.**
- [rag.md](rag.md) — Retrieval-Augmented Generation pattern with Redis (retrieve → augment → generate).
- [vector-database.md](vector-database.md) — vector storage + similarity search (embeddings, KNN).
- [redis-in-ai.md](redis-in-ai.md) — overview of where Redis fits in AI stacks.

Supporting AI/agent files:
- [redis-iris/redis-langcache.md](redis-iris/redis-langcache.md) — semantic LLM response cache.
- [redis-iris/redis-context-engine.md](redis-iris/redis-iris-context-engine.md) — context engine overview.
- [redis-iris/redis-context-retriever.md](redis-iris/redis-context-retriever.md) — context retrieval.

## Concepts & data model

- [redis-data-types.md](redis-data-types.md) — strings, hashes, lists, sets, sorted sets, streams, JSON, etc.
- [data-store.md](data-store.md) — Redis as a primary data store.
- [document-database.md](document-database.md) — JSON documents + querying.
- [faq.md](faq.md) — common questions, persistence, eviction, etc.

## Commands

- [redis-8-8-commands.md](redis-8-8-commands.md) — **full reference, grep-only** (see reading
  rules). Command groups: strings, hashes, lists, sets, sorted sets, streams, bitmaps,
  hyperloglog, geospatial, JSON, search, time series, vector set, pub/sub, transactions,
  scripting, connection, server, cluster, generic.
- [commands/pipelining.md](commands/pipelining.md) — batching requests.
- [commands/transactions.md](commands/transactions.md) — MULTI/EXEC/WATCH.
- [commands/keyspace.md](commands/keyspace.md) — key management & namespacing.
- [commands/multi-key-operations.md](commands/multi-key-operations.md) — operating across keys.

## Tooling

- [client-tools/cli.md](client-tools/cli.md) — `redis-cli` (grep for the flag/subcommand).
- [client-tools/redis-for-vs-code.md](client-tools/redis-for-vs-code.md) — VS Code extension.

---

> **Once the project stack is locked**, this index should be tightened: pin the exact command
> groups in use (likely JSON + Search/Vector + Strings/Hashes + Streams) and demote the rest.
> Until then it stays stack-agnostic.
