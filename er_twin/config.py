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


settings = Settings()
