"""Pytest configuration — runs before any test module is imported.

Bridges the gap between pydantic-settings (.env file) and os.getenv() calls
used by skip guards in test modules. Without this, integration tests skip even
when credentials are present in .env because os.getenv() only reads the shell
environment, not .env.
"""

import os

import pytest

from er_twin.config import settings

# Populate the shell environment from whatever pydantic-settings resolved so
# that os.getenv() calls in skip guards (test_storage.py, test_memory.py) see
# the same values as the app does.
_BRIDGE = {
    "REDIS_URL": settings.redis_url,
    "AGENT_MEMORY_BASE_URL": settings.agent_memory_base_url,
    "AGENT_MEMORY_STORE_ID": settings.agent_memory_store_id,
    "AGENT_MEMORY_API_KEY": settings.agent_memory_api_key,
}

for key, value in _BRIDGE.items():
    if value:
        os.environ.setdefault(key, value)


@pytest.fixture(autouse=True)
def _isolate_ehr_master(tmp_path, monkeypatch):
    """Redirect the EHR master fixture to a per-test temp file.

    Intake now calls `build_live_record`, which writes a stub entry back to the master EHR for
    new/walk-in patients (EHR-FLOW-004). Without this redirect, running the intake/orchestrator
    tests would mutate the committed `fixtures/ehr_master.json`. Tests that pass an explicit `path`
    (test_ehr.py) are unaffected; the live app keeps using the real fixture from settings.
    """
    import er_twin.ehr as ehr_mod

    master = tmp_path / "ehr_master.json"
    master.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(settings, "ehr_master_path", str(master))
    ehr_mod._master_cache.clear()
    yield
    ehr_mod._master_cache.clear()
