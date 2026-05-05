from __future__ import annotations

from typing import Any

from .usage_governance import budget_window_for


def reconcile_usage_ledger(
    repository,
    coordinator,
    *,
    period_kind: str,
    as_of: str | None = None,
    repair: bool = False,
    user_id: int | None = None,
    workspace_id: int | None = None,
) -> dict[str, Any]:
    window = budget_window_for(as_of, period_kind)
    summaries = repository.summarize_usage_ledger(
        period_kind=window.window,
        window_key=window.period_key,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    drift: list[dict[str, Any]] = []
    for summary in summaries:
        uid = int(summary["user_id"]) if summary.get("user_id") is not None else None
        wid = int(summary["workspace_id"]) if summary.get("workspace_id") is not None else None
        if uid is None or wid is None:
            continue
        expected = int(summary.get("event_count") or 0)
        actual = coordinator.describe_budget(user_id=uid, workspace_id=wid, period_key=window.period_key)
        if actual.get("user") != expected or actual.get("workspace") != expected:
            drift.append(
                {
                    "user_id": uid,
                    "workspace_id": wid,
                    "expected_user_count": expected,
                    "actual_user_count": actual.get("user"),
                    "expected_workspace_count": expected,
                    "actual_workspace_count": actual.get("workspace"),
                }
            )
            if repair:
                coordinator.set_budget_usage(
                    user_id=uid,
                    workspace_id=wid,
                    user_count=expected,
                    workspace_count=expected,
                    period_key=window.period_key,
                )
                repository.append_audit_log(
                    "budget.reconciliation.repaired",
                    user_id=uid,
                    workspace_id=wid,
                    resource_type="usage_ledger",
                    metadata={"period_kind": window.window, "window_key": window.period_key, "expected_count": expected},
                )
    return {
        "period_kind": window.window,
        "window_key": window.period_key,
        "repair_requested": repair,
        "repair_applied": bool(repair and drift),
        "drift": drift,
    }
