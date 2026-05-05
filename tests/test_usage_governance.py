from __future__ import annotations

import json

import pytest

from tradingagents.web.usage_governance import (
    JsonProviderUsageAdapter,
    ProviderUsageRecord,
    budget_window_for,
    import_provider_usage_records,
    normalize_budget_window,
    normalize_reconciliation_policy,
)


class FakeGovernanceRepository:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def append_usage_ledger_event(self, event_type: str, **kwargs):
        event = {"event_type": event_type, **kwargs}
        self.events.append(event)
        return event


def test_budget_window_helpers_validate_supported_reset_policies():
    assert budget_window_for("2026-05-05T15:30:00Z", "daily").period_key == "2026-05-05"
    assert budget_window_for("2026-05-05T15:30:00+00:00", "monthly").period_key == "2026-05"
    assert budget_window_for("2026-05-05T15:30:00+00:00", "never").period_key == "global"
    assert normalize_budget_window(" DAILY ") == "daily"
    assert normalize_reconciliation_policy(" REPORT ") == "report"

    with pytest.raises(ValueError, match="budget window"):
        normalize_budget_window("weekly")
    with pytest.raises(ValueError, match="reconciliation policy"):
        normalize_reconciliation_policy("overwrite")


def test_json_provider_usage_adapter_loads_mock_provider_records(tmp_path):
    usage_path = tmp_path / "provider-usage.json"
    usage_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "provider": "mock-provider",
                        "model": "gpt-5.5",
                        "started_at": "2026-05-05T15:00:00+00:00",
                        "ended_at": "2026-05-05T15:01:00+00:00",
                        "user_id": 7,
                        "workspace_id": 11,
                        "input_tokens": 100,
                        "output_tokens": 40,
                        "cost_cents": 12,
                        "external_ref": "usage-1",
                        "metadata": {"invoice_window": "test"},
                    }
                ]
            }
        )
    )

    records = JsonProviderUsageAdapter(usage_path).fetch_records()

    assert records == [
        ProviderUsageRecord(
            provider="mock-provider",
            model="gpt-5.5",
            started_at="2026-05-05T15:00:00+00:00",
            ended_at="2026-05-05T15:01:00+00:00",
            user_id=7,
            workspace_id=11,
            input_tokens=100,
            output_tokens=40,
            cost_cents=12,
            external_ref="usage-1",
            metadata={"invoice_window": "test"},
        )
    ]


def test_import_provider_usage_records_appends_auditable_ledger_events():
    repository = FakeGovernanceRepository()
    records = [
        ProviderUsageRecord(
            provider="mock-provider",
            model="gpt-5.5",
            started_at="2026-05-05T15:00:00+00:00",
            user_id=None,
            workspace_id=11,
            input_tokens=100,
            output_tokens=40,
            total_tokens=0,
            cost_cents=12,
            external_ref="usage-1",
        )
    ]

    imported = import_provider_usage_records(repository, records, actor_user_id=7)

    assert imported == repository.events
    assert imported[0]["event_type"] == "provider.usage.imported"
    assert imported[0]["allowed"] is True
    assert imported[0]["request_kind"] == "provider-import"
    assert imported[0]["user_id"] == 7
    assert imported[0]["workspace_id"] == 11
    assert imported[0]["provider"] == "mock-provider"
    assert imported[0]["model"] == "gpt-5.5"
    assert imported[0]["quantity"] == 140
    assert imported[0]["cost_cents"] == 12
    assert imported[0]["external_ref"] == "usage-1"
    assert imported[0]["metadata"]["input_tokens"] == 100
    assert imported[0]["metadata"]["output_tokens"] == 40
    assert imported[0]["metadata"]["total_tokens"] == 0
