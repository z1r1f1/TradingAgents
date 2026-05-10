from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WebSettings:
    runtime_mode: str = os.getenv("TRADINGAGENTS_WEB_RUNTIME_MODE", "local")
    database_path: Path = Path(os.getenv("TRADINGAGENTS_WEB_DB", "~/.tradingagents/web.sqlite3")).expanduser()
    postgres_dsn: str | None = os.getenv("TRADINGAGENTS_WEB_POSTGRES_DSN") or None
    redis_url: str | None = os.getenv("TRADINGAGENTS_WEB_REDIS_URL") or None
    coordination_namespace: str = os.getenv("TRADINGAGENTS_WEB_COORDINATION_NAMESPACE", "tradingagents:web")
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
    analysis_stale_after_seconds: int = int(os.getenv("TRADINGAGENTS_WEB_ANALYSIS_STALE_AFTER_SECONDS", "600"))
    analysis_workers: int = int(os.getenv("TRADINGAGENTS_WEB_ANALYSIS_WORKERS", "1"))
    real_runner_user_analysis_limit: int = int(os.getenv("TRADINGAGENTS_WEB_REAL_RUNNER_USER_ANALYSIS_LIMIT", "-1"))
    real_runner_workspace_analysis_limit: int = int(os.getenv("TRADINGAGENTS_WEB_REAL_RUNNER_WORKSPACE_ANALYSIS_LIMIT", "-1"))
    real_runner_budget_period: str = os.getenv("TRADINGAGENTS_WEB_REAL_RUNNER_BUDGET_PERIOD", "never")
    oidc_enabled: bool = os.getenv("TRADINGAGENTS_WEB_OIDC_ENABLED", "0").lower() in {"1", "true", "yes"}
    oidc_issuer_url: str | None = os.getenv("TRADINGAGENTS_WEB_OIDC_ISSUER_URL") or None
    oidc_authorization_endpoint: str | None = os.getenv("TRADINGAGENTS_WEB_OIDC_AUTHORIZATION_ENDPOINT") or None
    oidc_client_id: str | None = os.getenv("TRADINGAGENTS_WEB_OIDC_CLIENT_ID") or None
    oidc_client_secret: str | None = os.getenv("TRADINGAGENTS_WEB_OIDC_CLIENT_SECRET") or None
    oidc_redirect_uri: str | None = os.getenv("TRADINGAGENTS_WEB_OIDC_REDIRECT_URI") or None
    oidc_scope: str = os.getenv("TRADINGAGENTS_WEB_OIDC_SCOPE", "openid email profile")
    oidc_group_claim: str = os.getenv("TRADINGAGENTS_WEB_OIDC_GROUP_CLAIM", "groups")
    oidc_group_role_mapping_json: str = os.getenv("TRADINGAGENTS_WEB_OIDC_GROUP_ROLE_MAPPING", "{}")

    @property
    def oidc_group_role_mapping(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.oidc_group_role_mapping_json or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("OIDC group role mapping must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("OIDC group role mapping must be an object")
        return payload

    @property
    def is_production(self) -> bool:
        return self.web_env.lower() == "production"

    def validate_for_startup(self) -> None:
        normalized_runtime = self.runtime_mode.lower()
        if normalized_runtime not in {"local", "production-single", "production-cluster"}:
            raise ValueError("runtime mode must be local, production-single, or production-cluster")
        if normalized_runtime == "production-cluster":
            if not self.postgres_dsn:
                raise ValueError("production-cluster runtime requires Postgres configuration")
            if not self.redis_url:
                raise ValueError("production-cluster runtime requires Redis configuration")
        if self.analysis_workers < 1:
            raise ValueError("analysis workers must be at least 1")
        if self.oidc_enabled:
            missing = [
                name
                for name, value in {
                    "TRADINGAGENTS_WEB_OIDC_ISSUER_URL": self.oidc_issuer_url,
                    "TRADINGAGENTS_WEB_OIDC_CLIENT_ID": self.oidc_client_id,
                    "TRADINGAGENTS_WEB_OIDC_CLIENT_SECRET": self.oidc_client_secret,
                    "TRADINGAGENTS_WEB_OIDC_REDIRECT_URI": self.oidc_redirect_uri,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError(f"OIDC is enabled but required settings are missing: {', '.join(missing)}")
            self.oidc_group_role_mapping
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
