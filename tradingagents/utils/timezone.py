"""Timezone helpers for user-facing dates and timestamps."""

from __future__ import annotations

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Asia/Shanghai"


def get_configured_timezone_name() -> str:
    """Return the configured timezone name.

    TRADINGAGENTS_TIMEZONE takes precedence; TZ is the Docker/POSIX fallback.
    """

    return os.getenv("TRADINGAGENTS_TIMEZONE") or os.getenv("TZ") or DEFAULT_TIMEZONE


def get_configured_zoneinfo() -> ZoneInfo:
    name = get_configured_timezone_name()
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_TIMEZONE)


def now() -> datetime:
    """Current aware datetime in the configured TradingAgents timezone."""

    return datetime.now(get_configured_zoneinfo())


def today() -> date:
    """Current date in the configured TradingAgents timezone."""

    return now().date()


def timestamp(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Formatted current timestamp in the configured TradingAgents timezone."""

    return now().strftime(fmt)
