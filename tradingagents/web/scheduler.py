from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from collections.abc import Callable
from typing import Any

from .schemas import AnalysisCreate, ScheduledAnalysisCreate
from .service import AnalysisService


def parse_iso_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_iso_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _add_month(value: datetime) -> datetime:
    month = value.month + 1
    year = value.year
    if month > 12:
        month = 1
        year += 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def add_interval(value: datetime, interval: str) -> datetime:
    if interval == "daily":
        return value + timedelta(days=1)
    if interval == "weekly":
        return value + timedelta(weeks=1)
    if interval == "monthly":
        return _add_month(value)
    raise ValueError(f"unsupported interval: {interval}")


def compute_next_run_at(start_at: str | datetime, interval: str, *, after: str | datetime | None = None) -> str:
    candidate = parse_iso_datetime(start_at)
    boundary = parse_iso_datetime(after) if after is not None else datetime.now(timezone.utc)
    while candidate <= boundary:
        candidate = add_interval(candidate, interval)
    return format_iso_datetime(candidate)


class SchedulerService:
    def __init__(self, analysis_service: AnalysisService):
        self.analysis_service = analysis_service
        self.repository = analysis_service.repository

    def create_schedule(self, user_id: int, payload: ScheduledAnalysisCreate) -> dict[str, Any]:
        return self.repository.create_schedule(user_id, payload)

    def execute_schedule(self, user_id: int, schedule_id: int, *, run_inline: bool, triggered_by: str = "manual") -> dict[str, Any] | None:
        schedule = self.repository.get_schedule_for_user(schedule_id, user_id)
        if not schedule or schedule["status"] != "active":
            return None
        return self._execute_schedule_row(user_id, schedule, run_inline=run_inline, triggered_by=triggered_by)

    def run_due_for_user(
        self,
        user_id: int,
        *,
        now: str | None,
        run_inline: bool,
        workspace_id: int | None = None,
        before_execute: Callable[[dict[str, Any]], None] | None = None,
        lock_schedule: Callable[[dict[str, Any]], Any | None] | None = None,
        on_duplicate: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[dict[str, Any]]:
        now_value = format_iso_datetime(parse_iso_datetime(now)) if now else format_iso_datetime(datetime.now(timezone.utc))
        executions = []
        for schedule in self.repository.list_due_schedules_for_user(user_id, now_value, workspace_id=workspace_id):
            lock = lock_schedule(schedule) if lock_schedule else None
            if lock_schedule and lock is None:
                if on_duplicate:
                    on_duplicate(schedule)
                continue
            try:
                if before_execute:
                    before_execute(schedule)
                execution = self._execute_schedule_row(user_id, schedule, run_inline=run_inline, triggered_by="due", now=now_value)
                executions.append(execution)
            finally:
                if lock is not None:
                    lock.release()
        return executions

    def _execute_schedule_row(
        self,
        user_id: int,
        schedule: dict[str, Any],
        *,
        run_inline: bool,
        triggered_by: str,
        now: str | None = None,
    ) -> dict[str, Any]:
        started_at = now or format_iso_datetime(datetime.now(timezone.utc))
        execution = self.repository.create_schedule_execution(schedule["id"], status="running", started_at=started_at, triggered_by=triggered_by)
        params = self._analysis_params_for_schedule(schedule, started_at)
        try:
            task = self.analysis_service.create_analysis(user_id, params, run_inline=run_inline)
            if not run_inline:
                self.analysis_service.run_task(task["id"], params)
            completed_at = format_iso_datetime(datetime.now(timezone.utc))
            self.repository.complete_schedule_execution(execution["id"], task["id"], "completed", completed_at=completed_at)
            next_run_at = compute_next_run_at(schedule["next_run_at"], schedule["interval"], after=started_at)
            self.repository.update_schedule_after_execution(schedule["id"], last_run_at=started_at, next_run_at=next_run_at)
            return self.repository.get_schedule_execution(execution["id"])  # type: ignore[return-value]
        except Exception as exc:
            completed_at = format_iso_datetime(datetime.now(timezone.utc))
            self.repository.complete_schedule_execution(execution["id"], None, "failed", completed_at=completed_at, error=str(exc))
            raise

    def _analysis_params_for_schedule(self, schedule: dict[str, Any], run_at: str) -> AnalysisCreate:
        run_dt = parse_iso_datetime(run_at)
        analysis_date = schedule.get("analysis_date") or run_dt.date().isoformat()
        return AnalysisCreate(
            workspace_id=schedule.get("workspace_id"),
            ticker=schedule["ticker"],
            analysis_date=analysis_date,
            analysts=schedule["analysts"],
            research_depth=schedule["research_depth"],
            llm_provider=schedule["llm_provider"],
            backend_url=schedule.get("backend_url"),
            quick_model=schedule["quick_model"],
            deep_model=schedule["deep_model"],
            output_language=schedule["output_language"],
            google_thinking_level=schedule.get("google_thinking_level"),
            openai_reasoning_effort=schedule.get("openai_reasoning_effort"),
            anthropic_effort=schedule.get("anthropic_effort"),
            memory_ids=schedule.get("memory_ids", []),
        )
