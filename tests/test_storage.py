"""Storage interface contract tests. Phase 0 — TDD for InMemoryStore."""

from er_twin.storage import InMemoryStore


def test_set_and_get():
    store = InMemoryStore()
    store.set("er:patient:p1", {"name": "Jordan", "status": "waiting"})
    assert store.get("er:patient:p1")["name"] == "Jordan"


def test_get_missing_returns_empty_dict():
    store = InMemoryStore()
    assert store.get("er:patient:nope") == {}


def test_update_merges_fields():
    store = InMemoryStore()
    store.set("er:bed:bed1", {"status": "available"})
    store.update("er:bed:bed1", {"status": "occupied", "occupied_by": "p1"})
    record = store.get("er:bed:bed1")
    assert record["status"] == "occupied"
    assert record["occupied_by"] == "p1"


def test_update_creates_when_absent():
    store = InMemoryStore()
    store.update("er:nurse:n1", {"available": True})
    assert store.get("er:nurse:n1") == {"available": True}


def test_list_ids_filters_by_entity():
    store = InMemoryStore()
    store.set("er:patient:p1", {"x": 1})
    store.set("er:patient:p2", {"x": 2})
    store.set("er:bed:bed1", {"y": 1})
    assert sorted(store.list_ids("patient")) == ["p1", "p2"]
    assert store.list_ids("bed") == ["bed1"]


def test_get_returns_a_copy():
    store = InMemoryStore()
    store.set("er:patient:p1", {"name": "Jordan"})
    snapshot = store.get("er:patient:p1")
    snapshot["name"] = "Mutated"
    assert store.get("er:patient:p1")["name"] == "Jordan"


def test_publish_collects_messages():
    store = InMemoryStore()
    store.publish("er:events", "patient p1 admitted")
    store.publish("er:events", "bed bed1 occupied")
    assert store._channels["er:events"] == [
        "patient p1 admitted",
        "bed bed1 occupied",
    ]
