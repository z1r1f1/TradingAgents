from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .auth import expires_at, hash_password, new_token, token_hash, utcnow, verify_password
from .schemas import AnalysisCreate, EventPayload, ScheduledAnalysisCreate, ScheduledAnalysisUpdate


class WebRepository:
    def __init__(self, database_path: Path):
        self.database_path = Path(database_path).expanduser()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma foreign_keys = on")
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                create table if not exists users (
                    id integer primary key autoincrement,
                    email text not null unique,
                    password_hash text not null,
                    created_at text not null
                );
                create table if not exists sessions (
                    id integer primary key autoincrement,
                    user_id integer not null references users(id) on delete cascade,
                    token_hash text not null unique,
                    created_at text not null,
                    expires_at text not null,
                    last_seen_at text
                );
                create table if not exists analysis_tasks (
                    id integer primary key autoincrement,
                    user_id integer not null references users(id) on delete cascade,
                    status text not null,
                    created_at text not null,
                    updated_at text not null,
                    completed_at text,
                    error text
                );
                create table if not exists task_parameters (
                    id integer primary key autoincrement,
                    task_id integer not null unique references analysis_tasks(id) on delete cascade,
                    ticker text not null,
                    analysis_date text not null,
                    analysts_json text not null,
                    research_depth integer not null,
                    llm_provider text not null,
                    backend_url text,
                    quick_model text not null,
                    deep_model text not null,
                    output_language text not null,
                    google_thinking_level text,
                    openai_reasoning_effort text,
                    anthropic_effort text,
                    payload_json text not null
                );
                create table if not exists agent_event_logs (
                    id integer primary key autoincrement,
                    task_id integer not null references analysis_tasks(id) on delete cascade,
                    sequence integer not null,
                    agent text not null,
                    event_type text not null,
                    message text not null,
                    payload_json text not null,
                    created_at text not null,
                    unique(task_id, sequence)
                );
                create table if not exists report_sections (
                    id integer primary key autoincrement,
                    task_id integer not null references analysis_tasks(id) on delete cascade,
                    section_name text not null,
                    content text not null,
                    created_at text not null,
                    unique(task_id, section_name)
                );
                create table if not exists final_decisions (
                    id integer primary key autoincrement,
                    task_id integer not null unique references analysis_tasks(id) on delete cascade,
                    decision text not null,
                    confidence text,
                    rationale text,
                    raw_decision text,
                    payload_json text not null,
                    created_at text not null
                );
                create table if not exists schedules (
                    id integer primary key autoincrement,
                    user_id integer not null references users(id) on delete cascade,
                    name text not null,
                    status text not null,
                    ticker text not null,
                    start_at text not null,
                    next_run_at text not null,
                    last_run_at text,
                    interval text not null,
                    analysts_json text not null,
                    research_depth integer not null,
                    llm_provider text not null,
                    backend_url text,
                    quick_model text not null,
                    deep_model text not null,
                    output_language text not null,
                    analysis_date text,
                    analysis_date_policy text not null,
                    google_thinking_level text,
                    openai_reasoning_effort text,
                    anthropic_effort text,
                    created_at text not null,
                    updated_at text not null,
                    deleted_at text
                );
                create table if not exists schedule_executions (
                    id integer primary key autoincrement,
                    schedule_id integer not null references schedules(id) on delete cascade,
                    analysis_task_id integer references analysis_tasks(id) on delete set null,
                    status text not null,
                    triggered_by text not null,
                    started_at text not null,
                    completed_at text,
                    error text
                );
                """
            )

    def create_user(self, email: str, password: str) -> dict[str, Any]:
        now = utcnow()
        with self.connect() as conn:
            cur = conn.execute(
                "insert into users(email, password_hash, created_at) values (?, ?, ?)",
                (email, hash_password(password), now),
            )
            return {"id": cur.lastrowid, "email": email, "created_at": now}

    def get_user_by_email(self, email: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("select * from users where email = ?", (email,)).fetchone()

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select id, email, created_at from users where id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    def authenticate(self, email: str, password: str) -> dict[str, Any] | None:
        row = self.get_user_by_email(email)
        if not row or not verify_password(password, row["password_hash"]):
            return None
        return {"id": row["id"], "email": row["email"], "created_at": row["created_at"]}

    def create_session(self, user_id: int) -> str:
        token = new_token()
        with self.connect() as conn:
            conn.execute(
                "insert into sessions(user_id, token_hash, created_at, expires_at, last_seen_at) values (?, ?, ?, ?, ?)",
                (user_id, token_hash(token), utcnow(), expires_at(), utcnow()),
            )
        return token

    def get_user_for_token(self, token: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                select users.id, users.email, users.created_at
                from sessions join users on users.id = sessions.user_id
                where sessions.token_hash = ? and sessions.expires_at > ?
                """,
                (token_hash(token), utcnow()),
            ).fetchone()
            if row:
                conn.execute("update sessions set last_seen_at = ? where token_hash = ?", (utcnow(), token_hash(token)))
            return dict(row) if row else None

    def delete_session(self, token: str) -> None:
        with self.connect() as conn:
            conn.execute("delete from sessions where token_hash = ?", (token_hash(token),))

    def create_task(self, user_id: int, params: AnalysisCreate | dict[str, Any]) -> dict[str, Any]:
        if isinstance(params, dict):
            params = AnalysisCreate(**params)
        now = utcnow()
        payload = params.parameter_payload()
        with self.connect() as conn:
            cur = conn.execute(
                "insert into analysis_tasks(user_id, status, created_at, updated_at) values (?, 'queued', ?, ?)",
                (user_id, now, now),
            )
            task_id = cur.lastrowid
            conn.execute(
                """
                insert into task_parameters(
                    task_id, ticker, analysis_date, analysts_json, research_depth, llm_provider,
                    backend_url, quick_model, deep_model, output_language, google_thinking_level,
                    openai_reasoning_effort, anthropic_effort, payload_json
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    payload["ticker"],
                    payload["analysis_date"],
                    json.dumps(payload["analysts"]),
                    payload["research_depth"],
                    payload["llm_provider"],
                    payload.get("backend_url"),
                    payload["quick_model"],
                    payload["deep_model"],
                    payload["output_language"],
                    payload.get("google_thinking_level"),
                    payload.get("openai_reasoning_effort"),
                    payload.get("anthropic_effort"),
                    json.dumps(payload),
                ),
            )
        return self.get_task_for_user(task_id, user_id, include_detail=False)  # type: ignore[return-value]

    def update_task_status(self, task_id: int, status: str, error: str | None = None) -> None:
        completed_at = utcnow() if status in {"completed", "failed"} else None
        with self.connect() as conn:
            conn.execute(
                "update analysis_tasks set status = ?, updated_at = ?, completed_at = coalesce(?, completed_at), error = ? where id = ?",
                (status, utcnow(), completed_at, error, task_id),
            )

    def append_event(self, task_id: int, event: EventPayload | dict[str, Any]) -> dict[str, Any]:
        if isinstance(event, dict):
            event = EventPayload(**event)
        with self.connect() as conn:
            current = conn.execute("select coalesce(max(sequence), 0) from agent_event_logs where task_id = ?", (task_id,)).fetchone()[0]
            sequence = int(current) + 1
            created = utcnow()
            conn.execute(
                "insert into agent_event_logs(task_id, sequence, agent, event_type, message, payload_json, created_at) values (?, ?, ?, ?, ?, ?, ?)",
                (task_id, sequence, event.agent, event.event_type, event.message, json.dumps(event.payload), created),
            )
        return {"task_id": task_id, "sequence": sequence, "agent": event.agent, "event_type": event.event_type, "message": event.message, "payload": event.payload, "created_at": created}

    def save_report_sections(self, task_id: int, sections: dict[str, str]) -> None:
        with self.connect() as conn:
            for name, content in sections.items():
                conn.execute(
                    "insert into report_sections(task_id, section_name, content, created_at) values (?, ?, ?, ?) on conflict(task_id, section_name) do update set content = excluded.content",
                    (task_id, name, content or "", utcnow()),
                )

    def save_final_decision(self, task_id: int, decision: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                insert into final_decisions(task_id, decision, confidence, rationale, raw_decision, payload_json, created_at)
                values (?, ?, ?, ?, ?, ?, ?)
                on conflict(task_id) do update set decision = excluded.decision, confidence = excluded.confidence,
                    rationale = excluded.rationale, raw_decision = excluded.raw_decision, payload_json = excluded.payload_json
                """,
                (
                    task_id,
                    decision.get("decision", "HOLD"),
                    decision.get("confidence"),
                    decision.get("rationale"),
                    decision.get("raw_decision"),
                    json.dumps(decision),
                    utcnow(),
                ),
            )

    def list_tasks_for_user(self, user_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select t.*, p.ticker, p.analysis_date, fd.decision
                from analysis_tasks t
                join task_parameters p on p.task_id = t.id
                left join final_decisions fd on fd.task_id = t.id
                where t.user_id = ?
                order by t.created_at desc, t.id desc
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_task_for_user(self, task_id: int, user_id: int, *, include_detail: bool = True) -> dict[str, Any] | None:
        with self.connect() as conn:
            task = conn.execute("select * from analysis_tasks where id = ? and user_id = ?", (task_id, user_id)).fetchone()
            if not task:
                return None
            params = conn.execute("select * from task_parameters where task_id = ?", (task_id,)).fetchone()
            result = dict(task)
            if params:
                payload = json.loads(params["payload_json"])
                result["parameters"] = payload
            if include_detail:
                events = conn.execute("select * from agent_event_logs where task_id = ? order by sequence", (task_id,)).fetchall()
                sections = conn.execute("select section_name, content from report_sections where task_id = ? order by id", (task_id,)).fetchall()
                final = conn.execute("select * from final_decisions where task_id = ?", (task_id,)).fetchone()
                result["events"] = [self._event_dict(row) for row in events]
                result["report_sections"] = [dict(row) for row in sections]
                result["final_decision"] = json.loads(final["payload_json"]) if final else None
            return result


    def create_schedule(self, user_id: int, payload: ScheduledAnalysisCreate) -> dict[str, Any]:
        now = utcnow()
        start_at = self._format_datetime(payload.start_at)
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into schedules(
                    user_id, name, status, ticker, start_at, next_run_at, interval, analysts_json,
                    research_depth, llm_provider, backend_url, quick_model, deep_model, output_language,
                    analysis_date, analysis_date_policy, google_thinking_level, openai_reasoning_effort,
                    anthropic_effort, created_at, updated_at
                ) values (?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    payload.name,
                    payload.ticker,
                    start_at,
                    start_at,
                    payload.interval,
                    json.dumps(payload.analysts),
                    payload.research_depth,
                    payload.llm_provider,
                    payload.backend_url,
                    payload.quick_model,
                    payload.deep_model,
                    payload.output_language,
                    payload.analysis_date.isoformat() if payload.analysis_date else None,
                    payload.analysis_date_policy,
                    payload.google_thinking_level,
                    payload.openai_reasoning_effort,
                    payload.anthropic_effort,
                    now,
                    now,
                ),
            )
        return self.get_schedule_for_user(cur.lastrowid, user_id)  # type: ignore[return-value]

    def list_schedules_for_user(self, user_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "select * from schedules where user_id = ? and deleted_at is null order by created_at desc, id desc",
                (user_id,),
            ).fetchall()
        return [self._schedule_dict(row) for row in rows]

    def get_schedule_for_user(self, schedule_id: int, user_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "select * from schedules where id = ? and user_id = ? and deleted_at is null",
                (schedule_id, user_id),
            ).fetchone()
            if not row:
                return None
            schedule = self._schedule_dict(row)
            executions = conn.execute(
                "select * from schedule_executions where schedule_id = ? order by started_at desc, id desc limit 10",
                (schedule_id,),
            ).fetchall()
            schedule["executions"] = [dict(item) for item in executions]
            return schedule

    def update_schedule(self, schedule_id: int, user_id: int, payload: ScheduledAnalysisUpdate) -> dict[str, Any] | None:
        current = self.get_schedule_for_user(schedule_id, user_id)
        if not current:
            return None
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return current
        fields = []
        values: list[Any] = []
        for key, value in updates.items():
            db_key = key
            if key == "analysts":
                value = json.dumps(value)
                db_key = "analysts_json"
            elif key == "start_at" and value is not None:
                value = self._format_datetime(value)
                fields.append("next_run_at = ?")
                values.append(value)
            elif hasattr(value, "isoformat"):
                value = value.isoformat()
            fields.append(f"{db_key} = ?")
            values.append(value)
        fields.append("updated_at = ?")
        values.append(utcnow())
        values.extend([schedule_id, user_id])
        with self.connect() as conn:
            conn.execute(
                f"update schedules set {', '.join(fields)} where id = ? and user_id = ? and deleted_at is null",
                tuple(values),
            )
        return self.get_schedule_for_user(schedule_id, user_id)

    def set_schedule_status(self, schedule_id: int, user_id: int, status: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute(
                "update schedules set status = ?, updated_at = ? where id = ? and user_id = ? and deleted_at is null",
                (status, utcnow(), schedule_id, user_id),
            )
        return self.get_schedule_for_user(schedule_id, user_id)

    def delete_schedule(self, schedule_id: int, user_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "update schedules set deleted_at = ?, updated_at = ? where id = ? and user_id = ? and deleted_at is null",
                (utcnow(), utcnow(), schedule_id, user_id),
            )
            return cur.rowcount > 0

    def list_due_schedules_for_user(self, user_id: int, now: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select * from schedules
                where user_id = ? and status = 'active' and deleted_at is null and next_run_at <= ?
                order by next_run_at asc, id asc
                """,
                (user_id, now),
            ).fetchall()
        return [self._schedule_dict(row) for row in rows]

    def create_schedule_execution(self, schedule_id: int, *, status: str, started_at: str, triggered_by: str) -> dict[str, Any]:
        with self.connect() as conn:
            cur = conn.execute(
                "insert into schedule_executions(schedule_id, status, triggered_by, started_at) values (?, ?, ?, ?)",
                (schedule_id, status, triggered_by, started_at),
            )
        return self.get_schedule_execution(cur.lastrowid)  # type: ignore[return-value]

    def complete_schedule_execution(
        self,
        execution_id: int,
        analysis_task_id: int | None,
        status: str,
        *,
        completed_at: str,
        error: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "update schedule_executions set analysis_task_id = ?, status = ?, completed_at = ?, error = ? where id = ?",
                (analysis_task_id, status, completed_at, error, execution_id),
            )

    def get_schedule_execution(self, execution_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from schedule_executions where id = ?", (execution_id,)).fetchone()
            return dict(row) if row else None

    def update_schedule_after_execution(self, schedule_id: int, *, last_run_at: str, next_run_at: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "update schedules set last_run_at = ?, next_run_at = ?, updated_at = ? where id = ?",
                (last_run_at, next_run_at, utcnow(), schedule_id),
            )

    def _schedule_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["analysts"] = json.loads(data.pop("analysts_json"))
        return data

    def _format_datetime(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()

    def _event_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json"))
        return data
