"""State storage abstraction (LLD section 4).

Agents only ever call `StorageInterface`; they never import a concrete backend. `InMemoryStore` is
the default for local dev and tests. `RedisStore` (Phase 6) swaps in behind the same interface with
zero handler changes.

Key convention: `er:{entity}:{id}` (e.g. `er:patient:p1`, `er:bed:bed3`).
"""

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
        """Publish an event line to a channel (event log feed)."""


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
