"""Application configuration using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── App ──────────────────────────────────────────────────────────────
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_env: str = "development"
    app_debug: bool = False

    # ── Database ─────────────────────────────────────────────────────────
    database_host: str = "localhost"
    database_port: int = 6432  # PgBouncer port
    database_user: str = "app_user"
    database_password: str = "app_secret"
    database_name: str = "app_db"

    # ── Connection Pool (application-side, kept small for PgBouncer) ────
    db_pool_min_size: int = 2
    db_pool_max_size: int = 10
    db_pool_max_inactive_lifetime: float = 300.0  # seconds

    # ── Timeouts (milliseconds, passed as server_settings) ──────────────
    db_statement_timeout: int = 5_000  # 5 s
    db_idle_in_transaction_timeout: int = 10_000  # 10 s

    # ── Circuit Breaker ──────────────────────────────────────────────────
    cb_fail_max: int = 5
    cb_timeout_duration: int = 30  # seconds before half-open

    @property
    def dsn(self) -> str:
        """Build a PostgreSQL DSN string."""
        return (
            f"postgresql://{self.database_user}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )


# Singleton — import this everywhere
settings = Settings()
