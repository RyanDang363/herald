"""Pytest configuration — runs before any test module is imported.

Bridges the gap between pydantic-settings (.env file) and os.getenv() calls
used by skip guards in test modules. Without this, integration tests skip even
when credentials are present in .env because os.getenv() only reads the shell
environment, not .env.
"""

import os

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
