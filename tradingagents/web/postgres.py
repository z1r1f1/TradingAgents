from __future__ import annotations

import re
from typing import Any

from .database import WebRepository


class PgRow(dict):
    def __init__(self, columns: list[str], values: tuple[Any, ...]):
        super().__init__(zip(columns, values, strict=False))
        self._values = values

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


class PgCursor:
    def __init__(self, cursor, *, returning_id: bool = False):
        self._cursor = cursor
        self.rowcount = cursor.rowcount
        self.lastrowid = None
        if returning_id:
            row = cursor.fetchone()
            self.lastrowid = row[0] if row else None

    def _columns(self) -> list[str]:
        return [column.name for column in self._cursor.description or []]

    def fetchone(self):
        row = self._cursor.fetchone()
        return PgRow(self._columns(), row) if row is not None else None

    def fetchall(self):
        columns = self._columns()
        return [PgRow(columns, row) for row in self._cursor.fetchall()]


class PgConnection:
    ID_TABLES = {
        "users",
        "workspaces",
        "audit_logs",
        "sessions",
        "analysis_tasks",
        "task_parameters",
        "agent_event_logs",
        "report_sections",
        "final_decisions",
        "schedules",
        "schedule_executions",
        "agent_memories",
        "intervention_sessions",
        "intervention_messages",
        "intervention_events",
        "intervention_outputs",
    }

    def __init__(self, psycopg_conn):
        self._conn = psycopg_conn

    def __enter__(self) -> "PgConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()
        self._conn.close()

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> PgCursor:
        sql, returning_id = self._translate(query)
        cursor = self._conn.cursor()
        cursor.execute(sql, params)
        return PgCursor(cursor, returning_id=returning_id)

    def _translate(self, query: str) -> tuple[str, bool]:
        sql = re.sub(r"\?", "%s", query)
        stripped = sql.strip()
        lowered = stripped.lower()
        returning_id = False
        match = re.match(r"insert\s+into\s+([a-z_]+)", lowered)
        if match and match.group(1) in self.ID_TABLES and " returning " not in lowered and " on conflict" not in lowered:
            sql = f"{sql.rstrip()} returning id"
            returning_id = True
        return sql, returning_id


class PostgresSchemaManager:
    MIGRATION_VERSION = "phase7-production-cluster-runtime"

    @classmethod
    def required_tables(cls) -> list[str]:
        return [
            "users",
            "workspaces",
            "workspace_members",
            "schema_migrations",
            "audit_logs",
            "usage_ledger_events",
            "sessions",
            "analysis_tasks",
            "task_parameters",
            "agent_event_logs",
            "report_sections",
            "final_decisions",
            "schedules",
            "schedule_executions",
            "agent_memories",
            "analysis_memory_attachments",
            "schedule_memory_attachments",
            "intervention_sessions",
            "intervention_messages",
            "intervention_events",
            "intervention_outputs",
        ]

    def __init__(self, dsn: str):
        self.dsn = dsn

    def connect(self):
        try:
            import psycopg
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional install state
            raise ValueError("Postgres runtime requires psycopg; install the web production dependencies") from exc

        try:
            return psycopg.connect(self.dsn)
        except Exception as exc:  # pragma: no cover - exercised by integration environments
            raise ValueError("Postgres configuration is invalid or unreachable") from exc

    def initialize(self) -> None:
        with self.connect() as conn:
            for statement in self.schema_sql().split(";"):
                if statement.strip():
                    conn.execute(statement)
            conn.execute("alter table final_decisions add column if not exists confidence text")
            conn.execute("alter table final_decisions add column if not exists raw_decision text")
            conn.execute(
                "insert into schema_migrations(version, applied_at) values (%s, now()) on conflict(version) do nothing",
                (self.MIGRATION_VERSION,),
            )

    def check_health(self) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute("select 1").fetchone()
        return {"ok": True, "backend": "postgres"}

    def schema_sql(self) -> str:
        return """
        create table if not exists users (
            id bigserial primary key,
            email text not null unique,
            password_hash text not null,
            created_at text not null
        );
        create table if not exists workspaces (
            id bigserial primary key,
            name text not null,
            kind text not null,
            created_by_user_id bigint not null references users(id) on delete cascade,
            created_at text not null,
            updated_at text not null
        );
        create table if not exists workspace_members (
            workspace_id bigint not null references workspaces(id) on delete cascade,
            user_id bigint not null references users(id) on delete cascade,
            role text not null,
            created_at text not null,
            updated_at text not null,
            primary key (workspace_id, user_id)
        );
        create table if not exists schema_migrations (
            version text primary key,
            applied_at text not null
        );
        create table if not exists audit_logs (
            id bigserial primary key,
            user_id bigint references users(id) on delete set null,
            event_type text not null,
            resource_type text,
            resource_id text,
            metadata_json text not null,
            ip_address text,
            workspace_id bigint references workspaces(id) on delete set null,
            created_at text not null
        );
        create table if not exists usage_ledger_events (
            id bigserial primary key,
            user_id bigint references users(id) on delete set null,
            workspace_id bigint references workspaces(id) on delete set null,
            event_type text not null,
            resource_type text,
            resource_id text,
            allowed integer not null default 1,
            request_kind text not null,
            provider text,
            model text,
            period_kind text not null,
            window_key text not null,
            quantity integer not null default 1,
            cost_cents integer not null default 0,
            external_ref text,
            metadata_json text not null,
            occurred_at text not null,
            created_at text not null
        );
        create table if not exists sessions (
            id bigserial primary key,
            user_id bigint not null references users(id) on delete cascade,
            token_hash text not null unique,
            created_at text not null,
            expires_at text not null,
            last_seen_at text
        );
        create table if not exists analysis_tasks (
            id bigserial primary key,
            user_id bigint not null references users(id) on delete cascade,
            workspace_id bigint references workspaces(id) on delete cascade,
            status text not null,
            created_at text not null,
            updated_at text not null,
            completed_at text,
            error text
        );
        create table if not exists task_parameters (
            id bigserial primary key,
            task_id bigint not null unique references analysis_tasks(id) on delete cascade,
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
            id bigserial primary key,
            task_id bigint not null references analysis_tasks(id) on delete cascade,
            sequence integer not null,
            agent text not null,
            event_type text not null,
            message text not null,
            payload_json text not null,
            created_at text not null,
            unique(task_id, sequence)
        );
        create table if not exists report_sections (
            id bigserial primary key,
            task_id bigint not null references analysis_tasks(id) on delete cascade,
            section_name text not null,
            content text not null,
            created_at text not null,
            unique(task_id, section_name)
        );
        create table if not exists final_decisions (
            id bigserial primary key,
            task_id bigint not null unique references analysis_tasks(id) on delete cascade,
            decision text not null,
            confidence text,
            rationale text not null,
            raw_decision text,
            payload_json text not null,
            created_at text not null
        );
        create table if not exists schedules (
            id bigserial primary key,
            user_id bigint not null references users(id) on delete cascade,
            workspace_id bigint references workspaces(id) on delete cascade,
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
            id bigserial primary key,
            schedule_id bigint not null references schedules(id) on delete cascade,
            analysis_task_id bigint references analysis_tasks(id) on delete set null,
            status text not null,
            triggered_by text not null,
            started_at text not null,
            completed_at text,
            error text
        );
        create table if not exists agent_memories (
            id bigserial primary key,
            user_id bigint not null references users(id) on delete cascade,
            workspace_id bigint references workspaces(id) on delete cascade,
            source_analysis_task_id bigint not null references analysis_tasks(id) on delete cascade,
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
            analysis_task_id bigint not null references analysis_tasks(id) on delete cascade,
            memory_id bigint not null references agent_memories(id) on delete cascade,
            created_at text not null,
            primary key (analysis_task_id, memory_id)
        );
        create table if not exists schedule_memory_attachments (
            schedule_id bigint not null references schedules(id) on delete cascade,
            memory_id bigint not null references agent_memories(id) on delete cascade,
            created_at text not null,
            primary key (schedule_id, memory_id)
        );
        create table if not exists intervention_sessions (
            id bigserial primary key,
            user_id bigint not null references users(id) on delete cascade,
            workspace_id bigint references workspaces(id) on delete cascade,
            source_analysis_task_id bigint not null references analysis_tasks(id) on delete cascade,
            target_agent_name text not null,
            status text not null,
            created_at text not null,
            updated_at text not null,
            closed_at text
        );
        create table if not exists intervention_messages (
            id bigserial primary key,
            session_id bigint not null references intervention_sessions(id) on delete cascade,
            sequence integer not null,
            author text not null,
            content text not null,
            created_at text not null,
            unique(session_id, sequence)
        );
        create table if not exists intervention_events (
            id bigserial primary key,
            session_id bigint not null references intervention_sessions(id) on delete cascade,
            sequence integer not null,
            event_type text not null,
            message text not null,
            payload_json text not null,
            created_at text not null,
            unique(session_id, sequence)
        );
        create table if not exists intervention_outputs (
            id bigserial primary key,
            session_id bigint not null references intervention_sessions(id) on delete cascade,
            target_agent_name text not null,
            content text not null,
            context_json text not null,
            created_at text not null
        );
        """


class PostgresWebRepository(WebRepository):
    storage_backend = "postgres"

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.init_db()

    def connect(self) -> PgConnection:
        return PgConnection(PostgresSchemaManager(self.dsn).connect())

    def init_db(self) -> None:
        PostgresSchemaManager(self.dsn).initialize()
