"""Agent memory abstraction for the Orchestrator (LLD §4 — Agent Memory Contract).

The Orchestrator uses this module to record ER events into session memory and to
recall relevant prior context when producing summaries.

Two implementations:
  - IrisMemory  — real, backed by Redis Agent Memory (Iris) on Redis Cloud.
  - NoopMemory  — silent no-op; used when AGENT_MEMORY_* vars are absent or USE_MOCK=true.

The make_memory() factory picks the right backend automatically so agent code never
needs an if/else — it just calls record_event() and recall().

Session convention: a single stable session id (`er-orchestrator-session`) per Bureau
run. All ER events in one demo session live under one session so Iris can cross-reference
them during semantic recall.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


_SESSION_ID = "er-orchestrator-session"
_ACTOR_ID = "orchestrator"


class MemoryInterface(ABC):
    @abstractmethod
    def record_event(self, text: str) -> None:
        """Append a session event describing a completed ER action."""

    @abstractmethod
    def recall(self, query: str) -> list[str]:
        """Return a list of relevant prior event texts matching the query."""


class IrisMemory(MemoryInterface):
    """Real Iris / Redis Agent Memory implementation.

    Writes session events with tz-aware UTC timestamps (required by the Iris SDK).
    Semantic recall searches long-term memory that Iris automatically promotes from
    session history.

    @spec MEM-FLOW-001, MEM-FLOW-002
    """

    def __init__(self, base_url: str, store_id: str, api_key: str) -> None:
        from redis_agent_memory import AgentMemory  # lazy import

        self._client = AgentMemory(base_url, store_id=store_id, api_key=api_key)

    def record_event(self, text: str) -> None:
        # @spec MEM-FLOW-001
        from datetime import datetime, timezone

        from redis_agent_memory import models

        self._client.add_session_event(
            session_id=_SESSION_ID,
            actor_id=_ACTOR_ID,
            role=models.MessageRole.ASSISTANT,
            content=[{"text": text}],
            created_at=datetime.now(timezone.utc),
        )

    def recall(self, query: str) -> list[str]:
        # @spec MEM-FLOW-002
        try:
            results = self._client.search_long_term_memory(
                query=query,
                session_id=_SESSION_ID,
                limit=5,
            )
            memories = getattr(results, "memories", None) or []
            return [m.text for m in memories if hasattr(m, "text")]
        except Exception:
            return []

    def close(self) -> None:
        try:
            self._client.__exit__(None, None, None)
        except Exception:
            pass


class NoopMemory(MemoryInterface):
    """Silent no-op — used when Iris keys are absent or USE_MOCK=true.

    @spec MEM-ERR-001
    """

    def record_event(self, text: str) -> None:
        pass

    def recall(self, query: str) -> list[str]:
        return []


def make_memory() -> MemoryInterface:
    """Return IrisMemory when all AGENT_MEMORY_* vars are present and USE_MOCK is false,
    otherwise NoopMemory.

    @spec MEM-ERR-001
    """
    from er_twin.config import settings  # imported here to avoid circular imports

    if (
        not settings.use_mock
        and settings.agent_memory_base_url
        and settings.agent_memory_store_id
        and settings.agent_memory_api_key
    ):
        return IrisMemory(
            base_url=settings.agent_memory_base_url,
            store_id=settings.agent_memory_store_id,
            api_key=settings.agent_memory_api_key,
        )
    return NoopMemory()
