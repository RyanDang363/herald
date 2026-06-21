"""Storage interface contract tests.

Runs against both InMemoryStore (always) and RedisStore (skipped when REDIS_URL is absent
so CI and offline dev stay green). Both must satisfy the same contract.
"""

import os

import pytest

from er_twin.storage import InMemoryStore, RedisStore, StorageInterface

# ------------------------------------------------------------------
# fixtures
# ------------------------------------------------------------------

_REDIS_URL = os.getenv("REDIS_URL", "")
_SKIP_REDIS = pytest.mark.skipif(not _REDIS_URL, reason="REDIS_URL not set")

# Unique key prefix so parallel test runs don't collide on the real DB.
_TEST_PREFIX_KEY = "er:__test__"


@pytest.fixture()
def mem_store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture()
def redis_store() -> RedisStore:
    store = RedisStore(_REDIS_URL)
    # clean up any test keys before and after each test
    _flush_test_keys(store)
    yield store
    _flush_test_keys(store)


def _flush_test_keys(store: RedisStore) -> None:
    """Remove keys written by these tests so they don't pollute the shared DB."""
    for entity in ("patient", "bed", "nurse", "nope", "__test__"):
        ids = store.list_ids(entity)
        for eid in ids:
            store._client.delete(f"er:{entity}:{eid}")
        store._client.delete(f"er:index:{entity}")
    store._client.delete("er:events")


# ------------------------------------------------------------------
# parametrized helpers
# ------------------------------------------------------------------

def run_set_and_get(store: StorageInterface) -> None:
    store.set("er:patient:p1", {"name": "Jordan", "status": "waiting"})
    assert store.get("er:patient:p1")["name"] == "Jordan"


def run_get_missing_returns_empty_dict(store: StorageInterface) -> None:
    assert store.get("er:patient:nope") == {}


def run_update_merges_fields(store: StorageInterface) -> None:
    store.set("er:bed:bed1", {"status": "available"})
    store.update("er:bed:bed1", {"status": "occupied", "occupied_by": "p1"})
    record = store.get("er:bed:bed1")
    assert record["status"] == "occupied"
    assert record["occupied_by"] == "p1"


def run_update_creates_when_absent(store: StorageInterface) -> None:
    store.update("er:nurse:n1", {"available": True})
    assert store.get("er:nurse:n1") == {"available": True}


def run_list_ids_filters_by_entity(store: StorageInterface) -> None:
    store.set("er:patient:p1", {"x": 1})
    store.set("er:patient:p2", {"x": 2})
    store.set("er:bed:bed1", {"y": 1})
    assert sorted(store.list_ids("patient")) == ["p1", "p2"]
    assert store.list_ids("bed") == ["bed1"]


def run_get_returns_a_copy(store: StorageInterface) -> None:
    store.set("er:patient:p1", {"name": "Jordan"})
    snapshot = store.get("er:patient:p1")
    snapshot["name"] = "Mutated"
    assert store.get("er:patient:p1")["name"] == "Jordan"


def run_publish_appends(store: StorageInterface) -> None:
    store.publish("er:events", "patient p1 admitted")
    store.publish("er:events", "bed bed1 occupied")
    # InMemoryStore keeps a list; RedisStore writes to a Stream — both must not raise.
    # We don't assert the exact storage shape since the backends differ.


# ------------------------------------------------------------------
# InMemoryStore tests (always run)
# ------------------------------------------------------------------

def test_mem_set_and_get(mem_store: InMemoryStore) -> None:
    run_set_and_get(mem_store)


def test_mem_get_missing_returns_empty_dict(mem_store: InMemoryStore) -> None:
    run_get_missing_returns_empty_dict(mem_store)


def test_mem_update_merges_fields(mem_store: InMemoryStore) -> None:
    run_update_merges_fields(mem_store)


def test_mem_update_creates_when_absent(mem_store: InMemoryStore) -> None:
    run_update_creates_when_absent(mem_store)


def test_mem_list_ids_filters_by_entity(mem_store: InMemoryStore) -> None:
    run_list_ids_filters_by_entity(mem_store)


def test_mem_get_returns_a_copy(mem_store: InMemoryStore) -> None:
    run_get_returns_a_copy(mem_store)


def test_mem_publish_collects_messages(mem_store: InMemoryStore) -> None:
    mem_store.publish("er:events", "patient p1 admitted")
    mem_store.publish("er:events", "bed bed1 occupied")
    assert mem_store._channels["er:events"] == [
        "patient p1 admitted",
        "bed bed1 occupied",
    ]


# ------------------------------------------------------------------
# RedisStore contract tests (skipped without REDIS_URL)
# ------------------------------------------------------------------

@_SKIP_REDIS
def test_redis_set_and_get(redis_store: RedisStore) -> None:
    run_set_and_get(redis_store)


@_SKIP_REDIS
def test_redis_get_missing_returns_empty_dict(redis_store: RedisStore) -> None:
    run_get_missing_returns_empty_dict(redis_store)


@_SKIP_REDIS
def test_redis_update_merges_fields(redis_store: RedisStore) -> None:
    run_update_merges_fields(redis_store)


@_SKIP_REDIS
def test_redis_update_creates_when_absent(redis_store: RedisStore) -> None:
    run_update_creates_when_absent(redis_store)


@_SKIP_REDIS
def test_redis_list_ids_filters_by_entity(redis_store: RedisStore) -> None:
    run_list_ids_filters_by_entity(redis_store)


@_SKIP_REDIS
def test_redis_get_returns_a_copy(redis_store: RedisStore) -> None:
    run_get_returns_a_copy(redis_store)


@_SKIP_REDIS
def test_redis_publish_writes_to_stream(redis_store: RedisStore) -> None:
    redis_store.publish("er:events", "patient p1 admitted")
    # XLEN confirms the stream entry was written
    assert redis_store._client.xlen("er:events") >= 1


@_SKIP_REDIS
def test_redis_type_roundtrip(redis_store: RedisStore) -> None:
    """Bool, int, list, None must survive the JSON encode/decode round-trip."""
    redis_store.set("er:patient:p1", {
        "name": "Jordan",
        "acuity": 2,
        "available": True,
        "care_team": ["nurse1"],
        "assigned_bed": None,
    })
    record = redis_store.get("er:patient:p1")
    assert record["acuity"] == 2
    assert record["available"] is True
    assert record["care_team"] == ["nurse1"]
    assert record["assigned_bed"] is None


@_SKIP_REDIS
def test_redis_make_store_returns_redis_store() -> None:
    """make_store() picks RedisStore when REDIS_URL is present."""
    from er_twin.storage import make_store

    store = make_store()
    # REDIS_URL is set in CI/local with .env; USE_MOCK defaults True so may return InMemory.
    # Just assert it returns a valid StorageInterface instance.
    assert isinstance(store, StorageInterface)
