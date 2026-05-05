from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WebSettings:
    database_path: Path = Path(os.getenv("TRADINGAGENTS_WEB_DB", "~/.tradingagents/web.sqlite3")).expanduser()
    web_env: str = os.getenv("TRADINGAGENTS_WEB_ENV", "development")
    auth_secret: str = os.getenv("TRADINGAGENTS_WEB_AUTH_SECRET", "change-me-local-dev-secret")
    host: str = os.getenv("TRADINGAGENTS_WEB_HOST", "0.0.0.0")
    port: int = int(os.getenv("TRADINGAGENTS_WEB_PORT", "8000"))
    runner_mode: str = os.getenv("TRADINGAGENTS_WEB_RUNNER", "demo")
    allow_registration: bool = os.getenv("TRADINGAGENTS_WEB_ALLOW_REGISTRATION", "1").lower() not in {"0", "false", "no"}
    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv("TRADINGAGENTS_WEB_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        if origin.strip()
    )
    bootstrap_user_email: str | None = os.getenv("TRADINGAGENTS_WEB_BOOTSTRAP_EMAIL") or None
    bootstrap_user_password: str | None = os.getenv("TRADINGAGENTS_WEB_BOOTSTRAP_PASSWORD") or None
    rate_limit_window_seconds: int = int(os.getenv("TRADINGAGENTS_WEB_RATE_LIMIT_WINDOW_SECONDS", "60"))
    auth_rate_limit: int = int(os.getenv("TRADINGAGENTS_WEB_AUTH_RATE_LIMIT", "20"))
    mutation_rate_limit: int = int(os.getenv("TRADINGAGENTS_WEB_MUTATION_RATE_LIMIT", "60"))
    analysis_rate_limit: int = int(os.getenv("TRADINGAGENTS_WEB_ANALYSIS_RATE_LIMIT", "10"))
    intervention_rate_limit: int = int(os.getenv("TRADINGAGENTS_WEB_INTERVENTION_RATE_LIMIT", "20"))

    @property
    def is_production(self) -> bool:
        return self.web_env.lower() == "production"

    def validate_for_startup(self) -> None:
        if not self.is_production:
            return
        if self.allow_registration:
            raise ValueError("production mode rejects open self-registration")
        if self.auth_secret == "change-me-local-dev-secret" or len(self.auth_secret) < 24:
            raise ValueError("production mode requires a strong non-default auth secret")
        if not self.cors_origins or any("*" in origin or not origin.startswith("https://") for origin in self.cors_origins):
            raise ValueError("production mode requires explicit HTTPS non-wildcard CORS origins")
        if self.bootstrap_user_email and not self.bootstrap_user_password:
            raise ValueError("bootstrap user provisioning requires TRADINGAGENTS_WEB_BOOTSTRAP_PASSWORD")
