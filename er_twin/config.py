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

    # Dashboard (Dev 3) — read-only baseline
    dashboard_source: str = "fixture"  # "fixture" | "redis"
    dashboard_allow_input: bool = False
    # When true, the dashboard exposes an authenticated on-demand "Generate clip" action that drives
    # the offline Pika replay path (capture_replay_frames.py -> run_pika_keyframes.ps1 -> Claude CLI ->
    # Pika MCP). Off by default: it spends Pika credits and shells out to PowerShell + Chromium. The
    # er_twin agent runtime still never touches Pika — this lives only on the dashboard ops surface.
    dashboard_allow_pika: bool = False
    dashboard_port: int = 8050
    # Dashboard auth (demo gate — NOT real HIPAA compliance). Override in .env for anything real.
    dashboard_username: str = "admin"
    dashboard_password: str = "password"
    dashboard_secret_key: str = "dev-insecure-secret-change-me"  # signs the session cookie
    # Google OAuth (optional). When client id+secret are set, "Sign in with Google" is enabled.
    # Any authenticated Google account is allowed by the app (no allowlist), but Google Cloud
    # must be configured for External users / test users as needed. Register both redirects:
    # http://localhost:8050/auth/callback
    # http://127.0.0.1:8050/auth/callback
    google_client_id: str = ""
    google_client_secret: str = ""


settings = Settings()
