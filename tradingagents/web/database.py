from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .auth import expires_at, hash_password, new_token, token_hash, utcnow, verify_password
from .schemas import AnalysisCreate, EventPayload, MemoryUpdate, ScheduledAnalysisCreate, ScheduledAnalysisUpdate


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
                create table if not exists schema_migrations (
                    version text primary key,
                    applied_at text not null
                );
                create table if not exists audit_logs (
                    id integer primary key autoincrement,
                    user_id integer references users(id) on delete set null,
                    event_type text not null,
                    resource_type text,
                    resource_id text,
                    metadata_json text not null,
                    ip_address text,
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
                create table if not exists agent_memories (
                    id integer primary key autoincrement,
                    user_id integer not null references users(id) on delete cascade,
                    source_analysis_task_id integer not null references analysis_tasks(id) on delete cascade,
                    ticker text not null,
                    analysis_date text not null,
                    agent_name text not null,
                    title text not null,
                    content text not null,
                    tags_json text not null,
                    archived integer not null default 0,
                    created_at text not null
                );
                create table if not exists analysis_memory_attachments (
                    analysis_task_id integer not null references analysis_tasks(id) on delete cascade,
                    memory_id integer not null references agent_memories(id) on delete cascade,
                    created_at text not null,
                    primary key (analysis_task_id, memory_id)
                );
                create table if not exists schedule_memory_attachments (
                    schedule_id integer not null references schedules(id) on delete cascade,
                    memory_id integer not null references agent_memories(id) on delete cascade,
                    created_at text not null,
                    primary key (schedule_id, memory_id)
                );
                create table if not exists intervention_sessions (
                    id integer primary key autoincrement,
                    user_id integer not null references users(id) on delete cascade,
                    source_analysis_task_id integer not null references analysis_tasks(id) on delete cascade,
                    target_agent_name text not null,
                    status text not null,
                    created_at text not null,
                    updated_at text not null,
                    closed_at text
                );
                create table if not exists intervention_messages (
                    id integer primary key autoincrement,
                    session_id integer not null references intervention_sessions(id) on delete cascade,
                    sequence integer not null,
                    author text not null,
                    content text not null,
                    created_at text not null,
                    unique(session_id, sequence)
                );
                create table if not exists intervention_events (
                    id integer primary key autoincrement,
                    session_id integer not null references intervention_sessions(id) on delete cascade,
                    sequence integer not null,
                    event_type text not null,
                    message text not null,
                    payload_json text not null,
                    created_at text not null,
                    unique(session_id, sequence)
                );
                create table if not exists intervention_outputs (
                    id integer primary key autoincrement,
                    session_id integer not null references intervention_sessions(id) on delete cascade,
                    target_agent_name text not null,
                    content text not null,
                    context_json text not null,
                    created_at text not null
                );
                """
            )
            conn.execute(
                "insert or ignore into schema_migrations(version, applied_at) values (?, ?)",
                ("phase5-production-hardening", utcnow()),
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

    def append_audit_log(
        self,
        event_type: str,
        *,
        user_id: int | None = None,
        resource_type: str | None = None,
        resource_id: int | str | None = None,
        metadata: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        created_at = utcnow()
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into audit_logs(user_id, event_type, resource_type, resource_id, metadata_json, ip_address, created_at)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    event_type,
                    resource_type,
                    str(resource_id) if resource_id is not None else None,
                    json.dumps(metadata or {}),
                    ip_address,
                    created_at,
                ),
            )
            row = conn.execute("select * from audit_logs where id = ?", (cur.lastrowid,)).fetchone()
        return self._audit_log_dict(row)

    def list_audit_logs_for_user(self, user_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "select * from audit_logs where user_id = ? order by created_at desc, id desc",
                (user_id,),
            ).fetchall()
        return [self._audit_log_dict(row) for row in rows]

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
            for memory_id in self._validate_memory_ids(conn, user_id, payload.get("memory_ids", [])):
                conn.execute(
                    "insert into analysis_memory_attachments(analysis_task_id, memory_id, created_at) values (?, ?, ?)",
                    (task_id, memory_id, now),
                )
        return self.get_task_for_user(task_id, user_id, include_detail=False)  # type: ignore[return-value]


    def get_task_owner_id(self, task_id: int) -> int | None:
        with self.connect() as conn:
            row = conn.execute("select user_id from analysis_tasks where id = ?", (task_id,)).fetchone()
            return int(row["user_id"]) if row else None

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

    def export_user_data(self, user_id: int) -> dict[str, Any]:
        analyses = [self.get_task_for_user(task["id"], user_id) for task in self.list_tasks_for_user(user_id)]
        interventions = [self.get_intervention_for_user(session["id"], user_id) for session in self.list_interventions_for_user(user_id)]
        schedules = [self.get_schedule_for_user(schedule["id"], user_id) for schedule in self.list_schedules_for_user(user_id)]
        return {
            "format": "tradingagents.web.export.v1",
            "exported_at": utcnow(),
            "analyses": [item for item in analyses if item],
            "memories": self.list_memories_for_user(user_id, archived=None),
            "schedules": [item for item in schedules if item],
            "interventions": [item for item in interventions if item],
        }

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
                result["attached_memories"] = self.list_attached_memories(conn, task_id)
                result["intervention_sessions"] = self.list_interventions_for_task(conn, task_id)
            return result

    def delete_task_for_user(self, task_id: int, user_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute("delete from analysis_tasks where id = ? and user_id = ?", (task_id, user_id))
            return cur.rowcount > 0


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
        schedule_id = cur.lastrowid
        self.replace_schedule_memory_attachments(schedule_id, user_id, payload.memory_ids)
        return self.get_schedule_for_user(schedule_id, user_id)  # type: ignore[return-value]

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
            if key == "memory_ids":
                continue
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
        if payload.memory_ids is not None:
            self.replace_schedule_memory_attachments(schedule_id, user_id, payload.memory_ids)
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
        data["memory_ids"] = self.get_schedule_memory_ids(data["id"])
        return data

    def _format_datetime(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


    def _validate_memory_ids(self, conn: sqlite3.Connection, user_id: int, memory_ids: list[int]) -> list[int]:
        if not memory_ids:
            return []
        unique_ids = list(dict.fromkeys(int(memory_id) for memory_id in memory_ids))
        placeholders = ",".join("?" for _ in unique_ids)
        rows = conn.execute(
            f"select id from agent_memories where user_id = ? and archived = 0 and id in ({placeholders})",
            (user_id, *unique_ids),
        ).fetchall()
        found = {row["id"] for row in rows}
        if found != set(unique_ids):
            raise ValueError("one or more selected memories are unavailable")
        return unique_ids

    def extract_agent_memories(
        self,
        user_id: int,
        task_id: int,
        params: dict[str, Any],
        sections: dict[str, str],
    ) -> None:
        section_agents = {
            "market_report": "Market Analyst",
            "sentiment_report": "Social Analyst",
            "news_report": "News Analyst",
            "fundamentals_report": "Fundamentals Analyst",
            "investment_plan": "Research Manager",
            "trader_investment_plan": "Trader",
            "final_trade_decision": "Portfolio Manager",
        }
        ticker = params["ticker"]
        analysis_date = params["analysis_date"]
        with self.connect() as conn:
            for section, agent_name in section_agents.items():
                content = (sections.get(section) or "").strip()
                if not content:
                    continue
                conn.execute(
                    """
                    insert into agent_memories(
                        user_id, source_analysis_task_id, ticker, analysis_date, agent_name, title, content, tags_json, archived, created_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        user_id,
                        task_id,
                        ticker,
                        analysis_date,
                        agent_name,
                        f"{ticker} {agent_name} memory for {analysis_date}",
                        content,
                        json.dumps({"section": section}),
                        utcnow(),
                    ),
                )

    def list_memories_for_user(
        self,
        user_id: int,
        *,
        ticker: str | None = None,
        agent: str | None = None,
        analysis_date: str | None = None,
        query: str | None = None,
        archived: bool | None = False,
    ) -> list[dict[str, Any]]:
        clauses = ["user_id = ?"]
        values: list[Any] = [user_id]
        if ticker:
            clauses.append("ticker = ?")
            values.append(ticker.upper())
        if agent:
            clauses.append("agent_name = ?")
            values.append(agent)
        if analysis_date:
            clauses.append("analysis_date = ?")
            values.append(analysis_date)
        if archived is not None:
            clauses.append("archived = ?")
            values.append(1 if archived else 0)
        if query:
            clauses.append("(title like ? or content like ? or tags_json like ?)")
            like = f"%{query}%"
            values.extend([like, like, like])
        with self.connect() as conn:
            rows = conn.execute(
                f"select * from agent_memories where {' and '.join(clauses)} order by created_at desc, id desc",
                tuple(values),
            ).fetchall()
        return [self._memory_dict(row) for row in rows]

    def get_memory_for_user(self, memory_id: int, user_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select * from agent_memories where id = ? and user_id = ?", (memory_id, user_id)).fetchone()
            return self._memory_dict(row) if row else None

    def update_memory(self, memory_id: int, user_id: int, payload: MemoryUpdate) -> dict[str, Any] | None:
        current = self.get_memory_for_user(memory_id, user_id)
        if not current:
            return None
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return current
        fields = []
        values: list[Any] = []
        if "title" in updates:
            fields.append("title = ?")
            values.append(updates["title"])
        if "tags" in updates:
            fields.append("tags_json = ?")
            values.append(json.dumps(updates["tags"] or {}))
        values.extend([memory_id, user_id])
        with self.connect() as conn:
            conn.execute(f"update agent_memories set {', '.join(fields)} where id = ? and user_id = ?", tuple(values))
        return self.get_memory_for_user(memory_id, user_id)

    def set_memory_archived(self, memory_id: int, user_id: int, archived: bool) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute(
                "update agent_memories set archived = ? where id = ? and user_id = ?",
                (1 if archived else 0, memory_id, user_id),
            )
        return self.get_memory_for_user(memory_id, user_id)

    def list_attached_memories(self, conn: sqlite3.Connection, task_id: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            select m.* from agent_memories m
            join analysis_memory_attachments a on a.memory_id = m.id
            where a.analysis_task_id = ?
            order by a.created_at asc, m.id asc
            """,
            (task_id,),
        ).fetchall()
        return [self._memory_dict(row) for row in rows]

    def build_memory_context_for_task(self, task_id: int, *, max_chars: int = 4000) -> str | None:
        with self.connect() as conn:
            memories = self.list_attached_memories(conn, task_id)
        if not memories:
            return None
        parts = ["Attached historical agent memories:"]
        for memory in memories:
            parts.append(
                f"[Memory #{memory['id']}] {memory['agent_name']} | {memory['ticker']} | {memory['analysis_date']}\n"
                f"{memory['content']}"
            )
        context = "\n\n".join(parts)
        return context[:max_chars]

    def replace_schedule_memory_attachments(self, schedule_id: int, user_id: int, memory_ids: list[int] | None) -> None:
        if memory_ids is None:
            return
        with self.connect() as conn:
            valid_ids = self._validate_memory_ids(conn, user_id, memory_ids)
            conn.execute("delete from schedule_memory_attachments where schedule_id = ?", (schedule_id,))
            for memory_id in valid_ids:
                conn.execute(
                    "insert into schedule_memory_attachments(schedule_id, memory_id, created_at) values (?, ?, ?)",
                    (schedule_id, memory_id, utcnow()),
                )

    def get_schedule_memory_ids(self, schedule_id: int) -> list[int]:
        with self.connect() as conn:
            rows = conn.execute(
                "select memory_id from schedule_memory_attachments where schedule_id = ? order by created_at asc, memory_id asc",
                (schedule_id,),
            ).fetchall()
        return [row["memory_id"] for row in rows]

    def _memory_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["tags"] = json.loads(data.pop("tags_json"))
        data["archived"] = bool(data["archived"])
        return data


    def create_intervention_session(self, user_id: int, source_analysis_task_id: int, target_agent_name: str) -> dict[str, Any] | None:
        if not self.get_task_for_user(source_analysis_task_id, user_id, include_detail=False):
            return None
        now = utcnow()
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into intervention_sessions(user_id, source_analysis_task_id, target_agent_name, status, created_at, updated_at)
                values (?, ?, ?, 'open', ?, ?)
                """,
                (user_id, source_analysis_task_id, target_agent_name, now, now),
            )
        return self.get_intervention_for_user(cur.lastrowid, user_id)

    def list_interventions_for_user(self, user_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "select * from intervention_sessions where user_id = ? order by created_at desc, id desc",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_interventions_for_task(self, conn: sqlite3.Connection, task_id: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            "select * from intervention_sessions where source_analysis_task_id = ? order by created_at desc, id desc",
            (task_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_intervention_for_user(self, session_id: int, user_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "select * from intervention_sessions where id = ? and user_id = ?",
                (session_id, user_id),
            ).fetchone()
            if not row:
                return None
            session = dict(row)
            messages = conn.execute(
                "select * from intervention_messages where session_id = ? order by sequence asc",
                (session_id,),
            ).fetchall()
            events = conn.execute(
                "select * from intervention_events where session_id = ? order by sequence asc",
                (session_id,),
            ).fetchall()
            outputs = conn.execute(
                "select * from intervention_outputs where session_id = ? order by created_at asc, id asc",
                (session_id,),
            ).fetchall()
            session["messages"] = [dict(item) for item in messages]
            session["events"] = [self._intervention_event_dict(item) for item in events]
            session["outputs"] = [self._intervention_output_dict(item) for item in outputs]
            return session

    def delete_intervention_for_user(self, session_id: int, user_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute("delete from intervention_sessions where id = ? and user_id = ?", (session_id, user_id))
            return cur.rowcount > 0

    def append_intervention_message(self, session_id: int, user_id: int, content: str) -> dict[str, Any] | None:
        session = self.get_intervention_for_user(session_id, user_id)
        if not session or session["status"] != "open":
            return None
        with self.connect() as conn:
            current = conn.execute("select coalesce(max(sequence), 0) from intervention_messages where session_id = ?", (session_id,)).fetchone()[0]
            sequence = int(current) + 1
            created_at = utcnow()
            cur = conn.execute(
                "insert into intervention_messages(session_id, sequence, author, content, created_at) values (?, ?, 'user', ?, ?)",
                (session_id, sequence, content, created_at),
            )
            conn.execute("update intervention_sessions set updated_at = ? where id = ?", (created_at, session_id))
            row = conn.execute("select * from intervention_messages where id = ?", (cur.lastrowid,)).fetchone()
            return dict(row)

    def set_intervention_status(self, session_id: int, user_id: int, status: str) -> dict[str, Any] | None:
        current = self.get_intervention_for_user(session_id, user_id)
        if not current:
            return None
        closed_at = utcnow() if status == "closed" else None
        with self.connect() as conn:
            conn.execute(
                "update intervention_sessions set status = ?, updated_at = ?, closed_at = coalesce(?, closed_at) where id = ? and user_id = ?",
                (status, utcnow(), closed_at, session_id, user_id),
            )
        return self.get_intervention_for_user(session_id, user_id)

    def append_intervention_event(self, session_id: int, event_type: str, message: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.connect() as conn:
            current = conn.execute("select coalesce(max(sequence), 0) from intervention_events where session_id = ?", (session_id,)).fetchone()[0]
            sequence = int(current) + 1
            created_at = utcnow()
            cur = conn.execute(
                "insert into intervention_events(session_id, sequence, event_type, message, payload_json, created_at) values (?, ?, ?, ?, ?, ?)",
                (session_id, sequence, event_type, message, json.dumps(payload or {}), created_at),
            )
            row = conn.execute("select * from intervention_events where id = ?", (cur.lastrowid,)).fetchone()
            return self._intervention_event_dict(row)

    def create_intervention_output(self, session_id: int, *, target_agent_name: str, content: str, context: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as conn:
            cur = conn.execute(
                "insert into intervention_outputs(session_id, target_agent_name, content, context_json, created_at) values (?, ?, ?, ?, ?)",
                (session_id, target_agent_name, content, json.dumps(context), utcnow()),
            )
            row = conn.execute("select * from intervention_outputs where id = ?", (cur.lastrowid,)).fetchone()
            return self._intervention_output_dict(row)

    def _intervention_event_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json"))
        return data

    def _intervention_output_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["context"] = json.loads(data.pop("context_json"))
        return data

    def _audit_log_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json"))
        return data

    def _event_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json"))
        return data
