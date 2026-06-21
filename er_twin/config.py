"""Runtime configuration loaded from environment / .env (RONGERS standard: pydantic-settings)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    asione_api_key: str = ""
    redis_url: str = ""
    fal_key: str = ""
    agent_seed: str = "er-twin-demo-seed"
    use_mock: bool = True
    # Intake orchestration mode (decision 2026-06-20-intake-orchestration-mode): "direct" = canonical
    # in-process run_intake (demo-safe default); "async" = uAgent message flow (inert until built).
    intake_mode: str = "direct"

    # Iris Agent Memory (Phase 7) — leave blank to use NoopMemory
    agent_memory_base_url: str = ""
    agent_memory_store_id: str = ""
    agent_memory_api_key: str = ""

    # EHR master fixture path — override in tests via EHR_MASTER_PATH env var
    ehr_master_path: str = "fixtures/ehr_master.json"


settings = Settings()
