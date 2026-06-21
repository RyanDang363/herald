"""State storage abstraction (LLD section 4).

Agents only ever call `StorageInterface`; they never import a concrete backend. `InMemoryStore` is
the default for local dev and tests. `RedisStore` swaps in behind the same interface with zero
handler changes when `REDIS_URL` is set.

Key convention: `er:{entity}:{id}` (e.g. `er:patient:p1`, `er:bed:bed3`).
Index sets:     `er:index:{entity}` maintained automatically on set/update.
Event feed:     `er:events` as a Redis Stream (XADD) for durable, replayable history.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod


class StorageInterface(ABC):
    @abstractmethod
    def get(self, key: str) -> dict:
        """Return the record at `key`, or an empty dict if absent."""

    @abstractmethod
    def set(self, key: str, value: dict) -> None:
        """Replace the record at `key`."""

    @abstractmethod
    def update(self, key: str, partial: dict) -> None:
        """Merge `partial` into the record at `key`, creating it if absent."""

    @abstractmethod
    def list_ids(self, entity: str) -> list[str]:
        """Return all ids for an entity type (e.g. `patient` -> ['p1', 'p2'])."""

    @abstractmethod
    def publish(self, channel: str, msg: str) -> None:
        """Append an event line to the feed channel (Stream or in-memory list)."""


class InMemoryStore(StorageInterface):
    """Process-local dict implementation. No external dependencies."""

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}
        self._channels: dict[str, list[str]] = {}

    def get(self, key: str) -> dict:
        return dict(self._data.get(key, {}))

    def set(self, key: str, value: dict) -> None:
        self._data[key] = dict(value)

    def update(self, key: str, partial: dict) -> None:
        self._data.setdefault(key, {}).update(partial)

    def list_ids(self, entity: str) -> list[str]:
        prefix = f"er:{entity}:"
        return [key[len(prefix):] for key in self._data if key.startswith(prefix)]

    def publish(self, channel: str, msg: str) -> None:
        self._channels.setdefault(channel, []).append(msg)


class RedisStore(StorageInterface):
    """Redis-backed implementation using hashes, index sets, and Streams.

    Hashes:  `er:{entity}:{id}` — field values are JSON-encoded so types round-trip.
    Indexes: `er:index:{entity}` sets — maintained on every set/update so list_ids
             never needs KEYS/SCAN.
    Events:  `er:events` Stream via XADD so the dashboard can replay history with
             XRANGE (unlike pub/sub which drops messages with no live subscriber).

    Connection: module-level ConnectionPool shared across all RedisStore instances;
    socket timeouts configured per redis-connections guidance.
    """

    def __init__(self, redis_url: str) -> None:
        import redis as _redis  # local import keeps startup fast when USE_MOCK=true

        self._client = _redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=5.0,
            retry_on_timeout=True,
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _entity_and_id(key: str) -> tuple[str, str]:
        """Parse `er:{entity}:{id}` → ('entity', 'id')."""
        parts = key.split(":", 2)
        if len(parts) != 3 or parts[0] != "er":
            raise ValueError(f"Invalid ER key: {key!r}")
        return parts[1], parts[2]

    @staticmethod
    def _encode(value: dict) -> dict[str, str]:
        """JSON-encode each field value so native types survive the Redis round-trip."""
        return {k: json.dumps(v) for k, v in value.items()}

    @staticmethod
    def _decode(raw: dict[str, str]) -> dict:
        """JSON-decode field values returned from Redis."""
        result = {}
        for k, v in raw.items():
            try:
                result[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                result[k] = v
        return result

    # ------------------------------------------------------------------
    # StorageInterface
    # ------------------------------------------------------------------

    def get(self, key: str) -> dict:
        # @spec INTAKE-FLOW-002, SUMM-FLOW-001
        raw = self._client.hgetall(key)
        return self._decode(raw) if raw else {}

    def set(self, key: str, value: dict) -> None:
        # @spec INTAKE-FLOW-002, INTAKE-STATE-001
        entity, eid = self._entity_and_id(key)
        pipe = self._client.pipeline(transaction=False)
        pipe.delete(key)
        if value:
            pipe.hset(key, mapping=self._encode(value))
        pipe.sadd(f"er:index:{entity}", eid)
        pipe.execute()

    def update(self, key: str, partial: dict) -> None:
        # @spec INTAKE-FLOW-004, INTAKE-FLOW-006, INTAKE-FLOW-008
        entity, eid = self._entity_and_id(key)
        pipe = self._client.pipeline(transaction=False)
        if partial:
            pipe.hset(key, mapping=self._encode(partial))
        pipe.sadd(f"er:index:{entity}", eid)
        pipe.execute()

    def list_ids(self, entity: str) -> list[str]:
        # @spec SUMM-FLOW-001
        return list(self._client.smembers(f"er:index:{entity}"))

    def publish(self, channel: str, msg: str) -> None:
        # @spec MEM-FLOW-001 (event feed side)
        self._client.xadd(channel, {"msg": msg})


def make_store() -> StorageInterface:
    """Return a RedisStore when REDIS_URL is set and USE_MOCK is false, else InMemoryStore."""
    from er_twin.config import settings  # imported here to avoid circular imports at module level

    if settings.redis_url and not settings.use_mock:
        return RedisStore(settings.redis_url)
    return InMemoryStore()
