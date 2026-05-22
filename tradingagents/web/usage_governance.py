from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

SUPPORTED_BUDGET_WINDOWS = {"never", "daily", "monthly"}
SUPPORTED_RECONCILIATION_POLICIES = {"report", "repair"}


@dataclass(frozen=True)
class BudgetWindow:
    window: str
    period_key: str


@dataclass(frozen=True)
class ProviderUsageRecord:
    provider: str
    model: str | None
    started_at: str
    ended_at: str | None = None
    user_id: int | None = None
    workspace_id: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_cents: int = 0
    external_ref: str | None = None
    metadata: dict[str, Any] | None = None

    def as_metadata(self) -> dict[str, Any]:
        payload = dict(self.metadata or {})
        payload.setdefault("input_tokens", self.input_tokens)
        payload.setdefault("output_tokens", self.output_tokens)
        payload.setdefault("total_tokens", self.total_tokens)
        payload.setdefault("started_at", self.started_at)
        if self.ended_at:
            payload.setdefault("ended_at", self.ended_at)
        return payload


class ProviderUsageAdapter(Protocol):
    def fetch_records(self) -> list[ProviderUsageRecord]: ...


class JsonProviderUsageAdapter:
    def __init__(self, path: Path | str):
        self.path = Path(path).expanduser()

    def fetch_records(self) -> list[ProviderUsageRecord]:
        payload = json.loads(self.path.read_text())
        items = payload if isinstance(payload, list) else payload.get("items", [])
        return [ProviderUsageRecord(**item) for item in items]


class GovernanceRepository(Protocol):
    def append_usage_ledger_event(self, event_type: str, **kwargs: Any) -> dict[str, Any]: ...



def normalize_budget_window(window: str) -> str:
    normalized = (window or "never").strip().lower()
    if normalized not in SUPPORTED_BUDGET_WINDOWS:
        raise ValueError("budget window must be one of never, daily, monthly")
    return normalized



def normalize_reconciliation_policy(policy: str) -> str:
    normalized = (policy or "repair").strip().lower()
    if normalized not in SUPPORTED_RECONCILIATION_POLICIES:
        raise ValueError("reconciliation policy must be one of report, repair")
    return normalized



def parse_timestamp(value: str | None = None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)



def budget_window_for(moment: str | None, window: str) -> BudgetWindow:
    normalized = normalize_budget_window(window)
    when = parse_timestamp(moment)
    if normalized == "never":
        return BudgetWindow(window=normalized, period_key="global")
    if normalized == "daily":
        return BudgetWindow(window=normalized, period_key=when.strftime("%Y-%m-%d"))
    return BudgetWindow(window=normalized, period_key=when.strftime("%Y-%m"))



def import_provider_usage_records(
    repository: GovernanceRepository,
    records: list[ProviderUsageRecord],
    *,
    actor_user_id: int | None = None,
) -> list[dict[str, Any]]:
    imported: list[dict[str, Any]] = []
    for record in records:
        imported.append(
            repository.append_usage_ledger_event(
                "provider.usage.imported",
                allowed=True,
                request_kind="provider-import",
                user_id=record.user_id or actor_user_id,
                workspace_id=record.workspace_id,
                provider=record.provider,
                model=record.model,
                period_window="never",
                period_key="global",
                quantity=max(record.total_tokens, record.input_tokens + record.output_tokens, 0),
                cost_cents=record.cost_cents,
                external_ref=record.external_ref,
                metadata=record.as_metadata(),
            )
        )
    return imported



def provider_records_to_json(records: list[ProviderUsageRecord]) -> list[dict[str, Any]]:
    return [asdict(record) for record in records]
