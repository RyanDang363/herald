"""Runtime configuration loaded from environment / .env (pydantic-settings)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    asione_api_key: str = ""
    redis_url: str = ""
    agent_seed: str = "er-twin-demo-seed"
    use_mock: bool = True

    # Iris Agent Memory — leave blank to use NoopMemory
    agent_memory_base_url: str = ""
    agent_memory_store_id: str = ""
    agent_memory_api_key: str = ""

    # EHR master fixture path — override in tests via EHR_MASTER_PATH env var
    ehr_master_path: str = "fixtures/ehr_master.json"

    # Dashboard
    # source: "live" = shared in-process store (default when co-hosted with Bureau)
    #         "redis" = multi-process mode, agents and dashboard share a Redis instance
    #         "fixture" = offline/screenshot mode, static JSON fixture
    dashboard_source: str = "live"
    dashboard_allow_input: bool = False
    dashboard_port: int = 8050

    # Dashboard auth (demo gate — NOT real HIPAA compliance). Override in .env for anything real.
    # Defaults are deliberately weak so a fresh clone fails-loud rather than ships a silent backdoor.
    dashboard_username: str = "admin"
    dashboard_password: str = "password"
    dashboard_secret_key: str = "dev-insecure-secret-change-me"  # signs the session cookie

    # Google OAuth (optional). When client id+secret are set, "Sign in with Google" is enabled.
    # Register both redirects in Google Cloud Console:
    #   http://localhost:8050/auth/callback
    #   http://127.0.0.1:8050/auth/callback
    google_client_id: str = ""
    google_client_secret: str = ""
    # Comma-separated list of allowed Google emails. Empty = any authenticated Google account.
    google_allowed_emails: str = ""

    @property
    def allowed_email_set(self) -> set[str]:
        """Parsed email allowlist; empty set means any Google account is accepted."""
        return {e.strip() for e in self.google_allowed_emails.split(",") if e.strip()}


settings = Settings()
