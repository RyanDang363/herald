"""Memory interface contract tests.

NoopMemory tests always run. IrisMemory integration test runs only when
AGENT_MEMORY_* env vars are present.

@spec MEM-ERR-001, MEM-FLOW-001, MEM-FLOW-002
"""

import os

import pytest

from er_twin.memory import IrisMemory, MemoryInterface, NoopMemory, make_memory

# ------------------------------------------------------------------
# skip guard
# ------------------------------------------------------------------

_HAS_IRIS = all(
    os.getenv(v)
    for v in ("AGENT_MEMORY_BASE_URL", "AGENT_MEMORY_STORE_ID", "AGENT_MEMORY_API_KEY")
)
_SKIP_IRIS = pytest.mark.skipif(not _HAS_IRIS, reason="AGENT_MEMORY_* vars not set")

# ------------------------------------------------------------------
# NoopMemory tests (always run)
# ------------------------------------------------------------------


def test_noop_record_event_is_silent() -> None:
    # @spec MEM-ERR-001
    mem = NoopMemory()
    mem.record_event("patient p1 admitted")  # must not raise


def test_noop_recall_returns_empty_list() -> None:
    # @spec MEM-ERR-001
    mem = NoopMemory()
    result = mem.recall("any query")
    assert result == []


def test_noop_is_memory_interface() -> None:
    assert isinstance(NoopMemory(), MemoryInterface)


# ------------------------------------------------------------------
# make_memory factory tests
# ------------------------------------------------------------------


def test_make_memory_returns_noop_when_use_mock_true(monkeypatch: pytest.MonkeyPatch) -> None:
    # @spec MEM-ERR-001
    import er_twin.config as cfg_module

    monkeypatch.setattr(cfg_module.settings, "use_mock", True)
    monkeypatch.setattr(cfg_module.settings, "agent_memory_base_url", "https://example.com")
    monkeypatch.setattr(cfg_module.settings, "agent_memory_store_id", "abc123")
    monkeypatch.setattr(cfg_module.settings, "agent_memory_api_key", "key")
    mem = make_memory()
    assert isinstance(mem, NoopMemory)


def test_make_memory_returns_noop_when_keys_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    # @spec MEM-ERR-001
    import er_twin.config as cfg_module

    monkeypatch.setattr(cfg_module.settings, "use_mock", False)
    monkeypatch.setattr(cfg_module.settings, "agent_memory_base_url", "")
    monkeypatch.setattr(cfg_module.settings, "agent_memory_store_id", "")
    monkeypatch.setattr(cfg_module.settings, "agent_memory_api_key", "")
    mem = make_memory()
    assert isinstance(mem, NoopMemory)


def test_make_memory_returns_iris_when_keys_present(monkeypatch: pytest.MonkeyPatch) -> None:
    # @spec MEM-ERR-001 (positive path)
    import er_twin.config as cfg_module

    monkeypatch.setattr(cfg_module.settings, "use_mock", False)
    monkeypatch.setattr(cfg_module.settings, "agent_memory_base_url", "https://fake.memory.redis.io")
    monkeypatch.setattr(cfg_module.settings, "agent_memory_store_id", "fakestoreid")
    monkeypatch.setattr(cfg_module.settings, "agent_memory_api_key", "fakekey")
    mem = make_memory()
    assert isinstance(mem, IrisMemory)
    # Don't call network methods — just verify the type


# ------------------------------------------------------------------
# IrisMemory integration tests (skipped without real keys)
# ------------------------------------------------------------------


@_SKIP_IRIS
def test_iris_record_event_does_not_raise() -> None:
    # @spec MEM-FLOW-001
    mem = IrisMemory(
        base_url=os.environ["AGENT_MEMORY_BASE_URL"],
        store_id=os.environ["AGENT_MEMORY_STORE_ID"],
        api_key=os.environ["AGENT_MEMORY_API_KEY"],
    )
    mem.record_event("integration test event — patient p99 admitted to bed99")
    mem.close()


@_SKIP_IRIS
def test_iris_recall_returns_list() -> None:
    # @spec MEM-FLOW-002
    mem = IrisMemory(
        base_url=os.environ["AGENT_MEMORY_BASE_URL"],
        store_id=os.environ["AGENT_MEMORY_STORE_ID"],
        api_key=os.environ["AGENT_MEMORY_API_KEY"],
    )
    result = mem.recall("patient admitted")
    assert isinstance(result, list)
    mem.close()
