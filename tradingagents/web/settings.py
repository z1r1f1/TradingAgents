from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WebSettings:
    database_path: Path = Path(os.getenv("TRADINGAGENTS_WEB_DB", "~/.tradingagents/web.sqlite3")).expanduser()
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
