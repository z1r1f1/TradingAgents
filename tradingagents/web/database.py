from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .auth import expires_at, hash_password, new_token, token_hash, utcnow, verify_password
from .schemas import AnalysisCreate, EventPayload, MemoryUpdate, ScheduledAnalysisCreate, ScheduledAnalysisUpdate


class WebRepository:
    storage_backend = "sqlite"

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
                create table if not exists user_identity_links (
                    id integer primary key autoincrement,
                    user_id integer not null references users(id) on delete cascade,
                    provider text not null,
                    issuer text not null,
                    subject text not null,
                    email text not null,
                    groups_json text not null,
                    created_at text not null,
                    updated_at text not null,
                    last_login_at text not null,
                    unique(provider, issuer, subject)
                );
                create table if not exists workspaces (
                    id integer primary key autoincrement,
                    name text not null,
                    kind text not null,
                    created_by_user_id integer not null references users(id) on delete cascade,
                    created_at text not null,
                    updated_at text not null
                );
                create table if not exists workspace_members (
                    workspace_id integer not null references workspaces(id) on delete cascade,
                    user_id integer not null references users(id) on delete cascade,
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
                    id integer primary key autoincrement,
                    user_id integer references users(id) on delete set null,
                    event_type text not null,
                    resource_type text,
                    resource_id text,
                    metadata_json text not null,
                    ip_address text,
                    workspace_id integer references workspaces(id) on delete set null,
                    created_at text not null
                );
                create table if not exists usage_ledger_events (
                    id integer primary key autoincrement,
                    user_id integer references users(id) on delete set null,
                    workspace_id integer references workspaces(id) on delete set null,
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
                create table if not exists provisioning_events (
                    id integer primary key autoincrement,
                    workspace_id integer not null references workspaces(id) on delete cascade,
                    actor_user_id integer references users(id) on delete set null,
                    target_user_id integer references users(id) on delete set null,
                    target_email text not null,
                    action text not null,
                    role text,
                    status text not null,
                    external_id text,
                    metadata_json text not null,
                    created_at text not null
                );
                create table if not exists legal_holds (
                    id integer primary key autoincrement,
                    workspace_id integer not null references workspaces(id) on delete cascade,
                    resource_type text not null,
                    resource_id text,
                    reason text not null,
                    expires_at text,
                    created_by_user_id integer references users(id) on delete set null,
                    created_at text not null,
                    released_at text,
                    released_by_user_id integer references users(id) on delete set null,
                    release_reason text
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
                    workspace_id integer references workspaces(id) on delete cascade,
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
                    workspace_id integer references workspaces(id) on delete cascade,
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
                    workspace_id integer references workspaces(id) on delete cascade,
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
                    workspace_id integer references workspaces(id) on delete cascade,
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
            self._ensure_workspace_columns(conn)
            self._ensure_personal_workspaces(conn)
            conn.execute(
                "insert or ignore into schema_migrations(version, applied_at) values (?, ?)",
                ("phase5-production-hardening", utcnow()),
            )
            conn.execute(
                "insert or ignore into schema_migrations(version, applied_at) values (?, ?)",
                ("phase6-workspace-rbac-governance", utcnow()),
            )
            conn.execute(
                "insert or ignore into schema_migrations(version, applied_at) values (?, ?)",
                ("phase8-migration-usage-reconciliation", utcnow()),
            )
            conn.execute(
                "insert or ignore into schema_migrations(version, applied_at) values (?, ?)",
                ("phase9-enterprise-identity-retention", utcnow()),
            )
            conn.execute(
                "insert or ignore into schema_migrations(version, applied_at) values (?, ?)",
                ("phase10-enterprise-compliance-provisioning", utcnow()),
            )

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in conn.execute(f"pragma table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"alter table {table} add column {column} {definition}")

    def _ensure_workspace_columns(self, conn: sqlite3.Connection) -> None:
        self._ensure_column(conn, "analysis_tasks", "workspace_id", "integer references workspaces(id) on delete cascade")
        self._ensure_column(conn, "schedules", "workspace_id", "integer references workspaces(id) on delete cascade")
        self._ensure_column(conn, "agent_memories", "workspace_id", "integer references workspaces(id) on delete cascade")
        self._ensure_column(conn, "intervention_sessions", "workspace_id", "integer references workspaces(id) on delete cascade")
        self._ensure_column(conn, "audit_logs", "workspace_id", "integer references workspaces(id) on delete set null")

    def _ensure_personal_workspace_for_user(self, conn: sqlite3.Connection, user_id: int, email: str) -> int:
        row = conn.execute(
            """
            select w.id from workspaces w
            join workspace_members wm on wm.workspace_id = w.id
            where wm.user_id = ? and w.kind = 'personal'
            order by w.id limit 1
            """,
            (user_id,),
        ).fetchone()
        if row:
            return int(row["id"])
        now = utcnow()
        cur = conn.execute(
            "insert into workspaces(name, kind, created_by_user_id, created_at, updated_at) values (?, 'personal', ?, ?, ?)",
            (f"{email} personal", user_id, now, now),
        )
        workspace_id = int(cur.lastrowid)
        conn.execute(
            "insert into workspace_members(workspace_id, user_id, role, created_at, updated_at) values (?, ?, 'owner', ?, ?)",
            (workspace_id, user_id, now, now),
        )
        return workspace_id

    def _ensure_personal_workspaces(self, conn: sqlite3.Connection) -> None:
        users = conn.execute("select id, email from users").fetchall()
        for user in users:
            workspace_id = self._ensure_personal_workspace_for_user(conn, int(user["id"]), user["email"])
            for table in ("analysis_tasks", "schedules", "agent_memories", "intervention_sessions", "audit_logs"):
                conn.execute(
                    f"update {table} set workspace_id = ? where user_id = ? and workspace_id is null",
                    (workspace_id, int(user["id"])),
                )

    def create_user(self, email: str, password: str) -> dict[str, Any]:
        now = utcnow()
        with self.connect() as conn:
            cur = conn.execute(
                "insert into users(email, password_hash, created_at) values (?, ?, ?)",
                (email, hash_password(password), now),
            )
            user_id = int(cur.lastrowid)
            self._ensure_personal_workspace_for_user(conn, user_id, email)
            return {"id": user_id, "email": email, "created_at": now}

    def get_user_by_email(self, email: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("select * from users where email = ?", (email,)).fetchone()

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select id, email, created_at from users where id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    def upsert_oidc_user(self, *, issuer: str, subject: str, email: str, groups: list[str]) -> tuple[dict[str, Any], str]:
        normalized_email = email.strip().lower()
        now = utcnow()
        with self.connect() as conn:
            link = conn.execute(
                """
                select u.id, u.email, u.created_at
                from user_identity_links l join users u on u.id = l.user_id
                where l.provider = 'oidc' and l.issuer = ? and l.subject = ?
                """,
                (issuer, subject),
            ).fetchone()
        if link:
            action = "existing"
            user = dict(link)
        else:
            existing = self.get_user_by_email(normalized_email)
            if existing:
                action = "linked"
                user = {"id": int(existing["id"]), "email": existing["email"], "created_at": existing["created_at"]}
            else:
                action = "provisioned"
                user = self.create_user(normalized_email, new_token())
        with self.connect() as conn:
            conn.execute(
                """
                insert into user_identity_links(
                    user_id, provider, issuer, subject, email, groups_json, created_at, updated_at, last_login_at
                ) values (?, 'oidc', ?, ?, ?, ?, ?, ?, ?)
                on conflict(provider, issuer, subject) do update set
                    email = excluded.email,
                    groups_json = excluded.groups_json,
                    updated_at = excluded.updated_at,
                    last_login_at = excluded.last_login_at
                """,
                (user["id"], issuer, subject, normalized_email, json.dumps(groups), now, now, now),
            )
        return user, action

    def apply_oidc_group_mappings(
        self,
        *,
        user_id: int,
        groups: list[str],
        mapping: dict[str, Any],
    ) -> list[dict[str, Any]]:
        applied: list[dict[str, Any]] = []
        now = utcnow()
        allowed_roles = {"admin", "member", "viewer"}
        for group in groups:
            target = mapping.get(group)
            if not target:
                continue
            targets = target if isinstance(target, list) else [target]
            for item in targets:
                if not isinstance(item, dict):
                    continue
                workspace_id = item.get("workspace_id")
                role = str(item.get("role") or "").lower()
                if not workspace_id or role not in allowed_roles:
                    applied.append({"group": group, "workspace_id": workspace_id, "role": role, "applied": False})
                    continue
                with self.connect() as conn:
                    conn.execute(
                        """
                        insert into workspace_members(workspace_id, user_id, role, created_at, updated_at)
                        values (?, ?, ?, ?, ?)
                        on conflict(workspace_id, user_id) do update set
                            role = case when workspace_members.role = 'owner' then workspace_members.role else excluded.role end,
                            updated_at = excluded.updated_at
                        """,
                        (int(workspace_id), user_id, role, now, now),
                    )
                applied.append({"group": group, "workspace_id": int(workspace_id), "role": role, "applied": True})
        return applied

    def list_identity_links(self, *, workspace_id: int | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        join = "join users u on u.id = l.user_id"
        if workspace_id is not None:
            join += " join workspace_members wm on wm.user_id = u.id"
            clauses.append("wm.workspace_id = ?")
            values.append(workspace_id)
        where = f"where {' and '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                select l.*, u.email as user_email
                from user_identity_links l {join}
                {where}
                order by l.updated_at desc, l.id desc
                """,
                tuple(values),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["groups"] = json.loads(item.pop("groups_json"))
            item["email"] = item.pop("user_email")
            result.append(item)
        return result

    def provision_workspace_user(
        self,
        *,
        workspace_id: int,
        email: str,
        role: str,
        actor_user_id: int,
        external_id: str | None = None,
    ) -> dict[str, Any]:
        if role == "owner":
            raise ValueError("provisioning cannot grant workspace owner")
        normalized_email = email.strip().lower()
        user = self.get_user_by_email(normalized_email)
        action = "provision"
        if user is None:
            user = self.create_user(normalized_email, new_token())
            action = "provision_create_user"
        member = self.add_workspace_member(workspace_id, normalized_email, role)
        if not member:
            raise ValueError("provisioned user could not be attached to workspace")
        self.record_provisioning_event(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            target_user_id=int(user["id"]),
            target_email=normalized_email,
            action=action,
            role=role,
            status="active",
            external_id=external_id,
        )
        return member

    def update_provisioned_workspace_user(
        self,
        *,
        workspace_id: int,
        target_user_id: int,
        actor_user_id: int,
        role: str | None = None,
        active: bool | None = None,
        external_id: str | None = None,
    ) -> dict[str, Any]:
        if role == "owner":
            raise ValueError("provisioning cannot grant workspace owner")
        target = self.get_user(target_user_id)
        if not target:
            raise ValueError("target user not found")
        result: dict[str, Any] | None = None
        action = "provision_update"
        status = "active"
        if role:
            result = self.update_workspace_member_role(workspace_id, target_user_id, role)
            if result is None:
                raise ValueError("workspace member not found")
            action = "provision_role_update"
        if active is False:
            if not self.remove_workspace_member(workspace_id, target_user_id):
                raise ValueError("workspace member cannot be deactivated")
            result = {"workspace_id": workspace_id, "user_id": target_user_id, "email": target["email"], "role": role, "active": False}
            action = "provision_deactivate"
            status = "inactive"
        elif result is None:
            with self.connect() as conn:
                row = conn.execute(
                    """
                    select wm.workspace_id, wm.user_id, wm.role, wm.created_at, wm.updated_at, u.email
                    from workspace_members wm join users u on u.id = wm.user_id
                    where wm.workspace_id = ? and wm.user_id = ?
                    """,
                    (workspace_id, target_user_id),
                ).fetchone()
            if not row:
                raise ValueError("workspace member not found")
            result = dict(row)
        self.record_provisioning_event(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            target_email=target["email"],
            action=action,
            role=role or result.get("role"),
            status=status,
            external_id=external_id,
        )
        return result

    def record_provisioning_event(
        self,
        *,
        workspace_id: int,
        actor_user_id: int | None,
        target_user_id: int | None,
        target_email: str,
        action: str,
        role: str | None,
        status: str,
        external_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into provisioning_events(
                    workspace_id, actor_user_id, target_user_id, target_email, action, role, status,
                    external_id, metadata_json, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workspace_id,
                    actor_user_id,
                    target_user_id,
                    target_email,
                    action,
                    role,
                    status,
                    external_id,
                    json.dumps(metadata or {}),
                    utcnow(),
                ),
            )
            row = conn.execute("select * from provisioning_events where id = ?", (cur.lastrowid,)).fetchone()
        return self._provisioning_event_dict(row)

    def list_provisioning_events(self, *, workspace_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "select * from provisioning_events where workspace_id = ? order by created_at desc, id desc",
                (workspace_id,),
            ).fetchall()
        return [self._provisioning_event_dict(row) for row in rows]

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

    def get_personal_workspace_id(self, user_id: int) -> int:
        with self.connect() as conn:
            user = conn.execute("select id, email from users where id = ?", (user_id,)).fetchone()
            if not user:
                raise ValueError("user not found")
            return self._ensure_personal_workspace_for_user(conn, int(user["id"]), user["email"])

    def resolve_workspace_id(self, user_id: int, workspace_id: int | None = None) -> int:
        resolved = int(workspace_id) if workspace_id is not None else self.get_personal_workspace_id(user_id)
        if not self.get_workspace_role(user_id, resolved):
            raise PermissionError("workspace not found")
        return resolved

    def list_workspaces_for_user(self, user_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select w.*, wm.role
                from workspaces w join workspace_members wm on wm.workspace_id = w.id
                where wm.user_id = ?
                order by w.kind = 'personal' desc, w.created_at asc, w.id asc
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_workspace_for_user(self, workspace_id: int, user_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                select w.*, wm.role
                from workspaces w join workspace_members wm on wm.workspace_id = w.id
                where w.id = ? and wm.user_id = ?
                """,
                (workspace_id, user_id),
            ).fetchone()
            if not row:
                return None
            workspace = dict(row)
            members = conn.execute(
                """
                select wm.workspace_id, wm.user_id, wm.role, wm.created_at, wm.updated_at, u.email
                from workspace_members wm join users u on u.id = wm.user_id
                where wm.workspace_id = ?
                order by wm.role = 'owner' desc, u.email asc
                """,
                (workspace_id,),
            ).fetchall()
            workspace["members"] = [dict(member) for member in members]
            return workspace

    def get_workspace_role(self, user_id: int, workspace_id: int) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "select role from workspace_members where workspace_id = ? and user_id = ?",
                (workspace_id, user_id),
            ).fetchone()
        return str(row["role"]) if row else None

    def create_workspace(self, user_id: int, name: str) -> dict[str, Any]:
        now = utcnow()
        with self.connect() as conn:
            cur = conn.execute(
                "insert into workspaces(name, kind, created_by_user_id, created_at, updated_at) values (?, 'shared', ?, ?, ?)",
                (name, user_id, now, now),
            )
            workspace_id = int(cur.lastrowid)
            conn.execute(
                "insert into workspace_members(workspace_id, user_id, role, created_at, updated_at) values (?, ?, 'owner', ?, ?)",
                (workspace_id, user_id, now, now),
            )
        return self.get_workspace_for_user(workspace_id, user_id)  # type: ignore[return-value]

    def add_workspace_member(self, workspace_id: int, email: str, role: str) -> dict[str, Any] | None:
        user = self.get_user_by_email(email)
        if not user:
            return None
        now = utcnow()
        with self.connect() as conn:
            conn.execute(
                """
                insert into workspace_members(workspace_id, user_id, role, created_at, updated_at)
                values (?, ?, ?, ?, ?)
                on conflict(workspace_id, user_id) do update set role = excluded.role, updated_at = excluded.updated_at
                """,
                (workspace_id, int(user["id"]), role, now, now),
            )
            row = conn.execute(
                """
                select wm.workspace_id, wm.user_id, wm.role, wm.created_at, wm.updated_at, u.email
                from workspace_members wm join users u on u.id = wm.user_id
                where wm.workspace_id = ? and wm.user_id = ?
                """,
                (workspace_id, int(user["id"])),
            ).fetchone()
        return dict(row) if row else None

    def update_workspace_member_role(self, workspace_id: int, user_id: int, role: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            current = conn.execute(
                "select role from workspace_members where workspace_id = ? and user_id = ?",
                (workspace_id, user_id),
            ).fetchone()
            if not current:
                return None
            if current["role"] == "owner" and role != "owner":
                owner_count = conn.execute(
                    "select count(*) from workspace_members where workspace_id = ? and role = 'owner'",
                    (workspace_id,),
                ).fetchone()[0]
                if int(owner_count) <= 1:
                    raise ValueError("workspace must retain at least one owner")
            cur = conn.execute(
                "update workspace_members set role = ?, updated_at = ? where workspace_id = ? and user_id = ?",
                (role, utcnow(), workspace_id, user_id),
            )
            if cur.rowcount == 0:
                return None
            row = conn.execute(
                """
                select wm.workspace_id, wm.user_id, wm.role, wm.created_at, wm.updated_at, u.email
                from workspace_members wm join users u on u.id = wm.user_id
                where wm.workspace_id = ? and wm.user_id = ?
                """,
                (workspace_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def remove_workspace_member(self, workspace_id: int, user_id: int) -> bool:
        with self.connect() as conn:
            owner_count = conn.execute(
                "select count(*) from workspace_members where workspace_id = ? and role = 'owner'",
                (workspace_id,),
            ).fetchone()[0]
            current = conn.execute(
                "select role from workspace_members where workspace_id = ? and user_id = ?",
                (workspace_id, user_id),
            ).fetchone()
            if current and current["role"] == "owner" and int(owner_count) <= 1:
                return False
            cur = conn.execute("delete from workspace_members where workspace_id = ? and user_id = ?", (workspace_id, user_id))
            return cur.rowcount > 0

    def append_audit_log(
        self,
        event_type: str,
        *,
        user_id: int | None = None,
        resource_type: str | None = None,
        resource_id: int | str | None = None,
        workspace_id: int | None = None,
        metadata: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        created_at = utcnow()
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into audit_logs(user_id, event_type, resource_type, resource_id, metadata_json, ip_address, workspace_id, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    event_type,
                    resource_type,
                    str(resource_id) if resource_id is not None else None,
                    json.dumps(metadata or {}),
                    ip_address,
                    workspace_id,
                    created_at,
                ),
            )
            row = conn.execute("select * from audit_logs where id = ?", (cur.lastrowid,)).fetchone()
        return self._audit_log_dict(row)

    def list_audit_logs_for_user(
        self,
        user_id: int,
        *,
        workspace_id: int | None = None,
        event_type: str | None = None,
        target_user_id: int | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["(user_id = ? or workspace_id in (select workspace_id from workspace_members where user_id = ?))"]
        values: list[Any] = [user_id, user_id]
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            values.append(workspace_id)
        if event_type:
            clauses.append("event_type = ?")
            values.append(event_type)
        if target_user_id is not None:
            clauses.append("user_id = ?")
            values.append(target_user_id)
        if start_at:
            clauses.append("created_at >= ?")
            values.append(start_at)
        if end_at:
            clauses.append("created_at <= ?")
            values.append(end_at)
        with self.connect() as conn:
            rows = conn.execute(
                f"select * from audit_logs where {' and '.join(clauses)} order by created_at desc, id desc",
                tuple(values),
            ).fetchall()
        return [self._audit_log_dict(row) for row in rows]

    def list_audit_logs_for_workspace(self, workspace_id: int, *, event_type: str | None = None) -> list[dict[str, Any]]:
        clauses = ["workspace_id = ?"]
        values: list[Any] = [workspace_id]
        if event_type:
            clauses.append("event_type = ?")
            values.append(event_type)
        with self.connect() as conn:
            rows = conn.execute(
                f"select * from audit_logs where {' and '.join(clauses)} order by created_at desc, id desc",
                tuple(values),
            ).fetchall()
        return [self._audit_log_dict(row) for row in rows]

    def create_legal_hold(
        self,
        *,
        workspace_id: int,
        resource_type: str,
        resource_id: str | None,
        reason: str,
        created_by_user_id: int,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into legal_holds(
                    workspace_id, resource_type, resource_id, reason, expires_at, created_by_user_id, created_at
                ) values (?, ?, ?, ?, ?, ?, ?)
                """,
                (workspace_id, resource_type, resource_id, reason, expires_at, created_by_user_id, utcnow()),
            )
            row = conn.execute("select * from legal_holds where id = ?", (cur.lastrowid,)).fetchone()
        return self._legal_hold_dict(row)

    def list_legal_holds(self, *, workspace_id: int, active_only: bool = False) -> list[dict[str, Any]]:
        clauses = ["workspace_id = ?"]
        values: list[Any] = [workspace_id]
        if active_only:
            clauses.append("released_at is null")
        with self.connect() as conn:
            rows = conn.execute(
                f"select * from legal_holds where {' and '.join(clauses)} order by created_at desc, id desc",
                tuple(values),
            ).fetchall()
        return [self._legal_hold_dict(row) for row in rows]

    def release_legal_hold(self, *, workspace_id: int, hold_id: int, released_by_user_id: int, reason: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute(
                """
                update legal_holds
                set released_at = ?, released_by_user_id = ?, release_reason = ?
                where id = ? and workspace_id = ? and released_at is null
                """,
                (utcnow(), released_by_user_id, reason, hold_id, workspace_id),
            )
            row = conn.execute("select * from legal_holds where id = ? and workspace_id = ?", (hold_id, workspace_id)).fetchone()
        return self._legal_hold_dict(row) if row else None

    def retention_preview(self, *, workspace_id: int, resource_type: str, cutoff_before: str) -> dict[str, Any]:
        table, timestamp_column = self._retention_table(resource_type)
        matched_rows = self._retention_candidate_rows(workspace_id=workspace_id, resource_type=resource_type, cutoff_before=cutoff_before)
        held_ids = self._active_held_resource_ids(workspace_id=workspace_id, resource_type=resource_type)
        type_wide_hold = self._has_type_wide_legal_hold(workspace_id=workspace_id, resource_type=resource_type)
        held_rows = matched_rows if type_wide_hold else [row for row in matched_rows if str(row["id"]) in held_ids]
        eligible_count = 0 if type_wide_hold else len(matched_rows) - len(held_rows)
        return {
            "dry_run": True,
            "workspace_id": workspace_id,
            "resource_type": resource_type,
            "cutoff_before": cutoff_before,
            "matched_count": len(matched_rows),
            "eligible_count": eligible_count,
            "held_count": len(held_rows),
            "held_resources": [{"id": str(row["id"]), "resource_type": resource_type} for row in held_rows],
        }

    def retention_apply(
        self,
        *,
        workspace_id: int,
        resource_type: str,
        cutoff_before: str,
        archive_memories: bool = True,
    ) -> dict[str, Any]:
        table, timestamp_column = self._retention_table(resource_type)
        matched_rows = self._retention_candidate_rows(workspace_id=workspace_id, resource_type=resource_type, cutoff_before=cutoff_before)
        held_ids = self._active_held_resource_ids(workspace_id=workspace_id, resource_type=resource_type)
        type_wide_hold = self._has_type_wide_legal_hold(workspace_id=workspace_id, resource_type=resource_type)
        held_rows = matched_rows if type_wide_hold else [row for row in matched_rows if str(row["id"]) in held_ids]
        eligible_ids = [] if type_wide_hold else [int(row["id"]) for row in matched_rows if str(row["id"]) not in held_ids]
        with self.connect() as conn:
            if not eligible_ids:
                affected = 0
            elif resource_type == "memories" and archive_memories:
                placeholders = ", ".join("?" for _ in eligible_ids)
                cur = conn.execute(
                    f"update {table} set archived = 1 where id in ({placeholders}) and archived = 0",
                    tuple(eligible_ids),
                )
                affected = cur.rowcount
            else:
                placeholders = ", ".join("?" for _ in eligible_ids)
                cur = conn.execute(
                    f"delete from {table} where id in ({placeholders})",
                    tuple(eligible_ids),
                )
                affected = cur.rowcount
        return {
            "applied": True,
            "workspace_id": workspace_id,
            "resource_type": resource_type,
            "cutoff_before": cutoff_before,
            "matched_count": len(matched_rows),
            "affected_count": int(affected),
            "held_count": len(held_rows),
            "held_resources": [{"id": str(row["id"]), "resource_type": resource_type} for row in held_rows],
            "mode": "archive" if resource_type == "memories" and archive_memories else "delete",
        }

    def _retention_candidate_rows(self, *, workspace_id: int, resource_type: str, cutoff_before: str) -> list[dict[str, Any]]:
        table, timestamp_column = self._retention_table(resource_type)
        with self.connect() as conn:
            rows = conn.execute(
                f"select id from {table} where workspace_id = ? and {timestamp_column} < ? order by id",
                (workspace_id, cutoff_before),
            ).fetchall()
        return [dict(row) for row in rows]

    def _active_held_resource_ids(self, *, workspace_id: int, resource_type: str) -> set[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select resource_id from legal_holds
                where workspace_id = ? and resource_type = ? and released_at is null and resource_id is not null
                """,
                (workspace_id, resource_type),
            ).fetchall()
        return {str(row["resource_id"]) for row in rows}

    def _has_type_wide_legal_hold(self, *, workspace_id: int, resource_type: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                select 1 from legal_holds
                where workspace_id = ? and resource_type = ? and released_at is null and resource_id is null
                limit 1
                """,
                (workspace_id, resource_type),
            ).fetchone()
        return bool(row)

    def _retention_table(self, resource_type: str) -> tuple[str, str]:
        mapping = {
            "analyses": ("analysis_tasks", "created_at"),
            "schedules": ("schedules", "created_at"),
            "memories": ("agent_memories", "created_at"),
            "interventions": ("intervention_sessions", "created_at"),
            "audit_logs": ("audit_logs", "created_at"),
            "usage_ledger": ("usage_ledger_events", "occurred_at"),
        }
        if resource_type not in mapping:
            raise ValueError("unsupported retention resource type")
        return mapping[resource_type]


    def record_usage_ledger(
        self,
        *,
        user_id: int | None,
        workspace_id: int | None,
        resource_type: str | None = None,
        resource_id: int | str | None = None,
        event_type: str = "budget.usage.recorded",
        allowed: bool = True,
        request_kind: str = "analysis",
        provider: str | None = None,
        model: str | None = None,
        period_kind: str = "never",
        occurred_at: str | None = None,
        quantity: int = 1,
        cost_cents: int = 0,
        external_ref: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from .usage_governance import budget_window_for

        window = budget_window_for(occurred_at, period_kind)
        occurred = occurred_at or utcnow()
        created = utcnow()
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into usage_ledger_events(
                    user_id, workspace_id, event_type, resource_type, resource_id, allowed, request_kind,
                    provider, model, period_kind, window_key, quantity, cost_cents, external_ref,
                    metadata_json, occurred_at, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    workspace_id,
                    event_type,
                    resource_type,
                    str(resource_id) if resource_id is not None else None,
                    1 if allowed else 0,
                    request_kind,
                    provider,
                    model,
                    window.window,
                    window.period_key,
                    quantity,
                    cost_cents,
                    external_ref,
                    json.dumps(metadata or {}),
                    occurred,
                    created,
                ),
            )
            row = conn.execute("select * from usage_ledger_events where id = ?", (cur.lastrowid,)).fetchone()
        entry = self._usage_ledger_dict(row)
        self.append_audit_log(
            event_type,
            user_id=user_id,
            workspace_id=workspace_id,
            resource_type=resource_type or "usage_ledger",
            resource_id=resource_id,
            metadata={"ledger_event_id": entry["id"], "request_kind": request_kind, "window_key": entry["window_key"]},
        )
        return entry

    def append_usage_ledger_event(self, event_type: str, **kwargs: Any) -> dict[str, Any]:
        return self.record_usage_ledger(event_type=event_type, **kwargs)

    def update_latest_usage_ledger_resource(
        self,
        *,
        user_id: int,
        workspace_id: int,
        resource_type: str,
        resource_id: int | str,
    ) -> None:
        with self.connect() as conn:
            row = conn.execute(
                """
                select id from usage_ledger_events
                where user_id = ? and workspace_id = ? and resource_id is null
                order by id desc limit 1
                """,
                (user_id, workspace_id),
            ).fetchone()
            if row:
                conn.execute(
                    "update usage_ledger_events set resource_type = ?, resource_id = ? where id = ?",
                    (resource_type, str(resource_id), row["id"]),
                )

    def list_usage_ledger(
        self,
        *,
        user_id: int | None = None,
        workspace_id: int | None = None,
        period_kind: str | None = None,
        window_key: str | None = None,
        allowed: bool | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if user_id is not None:
            clauses.append("user_id = ?")
            values.append(user_id)
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            values.append(workspace_id)
        if period_kind is not None:
            clauses.append("period_kind = ?")
            values.append(period_kind)
        if window_key is not None:
            clauses.append("window_key = ?")
            values.append(window_key)
        if allowed is not None:
            clauses.append("allowed = ?")
            values.append(1 if allowed else 0)
        where = f"where {' and '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"select * from usage_ledger_events {where} order by occurred_at asc, id asc",
                tuple(values),
            ).fetchall()
        return [self._usage_ledger_dict(row) for row in rows]

    def summarize_usage_ledger(
        self,
        *,
        period_kind: str,
        window_key: str,
        user_id: int | None = None,
        workspace_id: int | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["period_kind = ?", "window_key = ?", "allowed = 1"]
        values: list[Any] = [period_kind, window_key]
        if user_id is not None:
            clauses.append("user_id = ?")
            values.append(user_id)
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            values.append(workspace_id)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                select user_id, workspace_id, count(*) as event_count, coalesce(sum(quantity), 0) as quantity,
                       coalesce(sum(cost_cents), 0) as cost_cents
                from usage_ledger_events
                where {' and '.join(clauses)}
                group by user_id, workspace_id
                order by user_id, workspace_id
                """,
                tuple(values),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_task(self, user_id: int, params: AnalysisCreate | dict[str, Any]) -> dict[str, Any]:
        if isinstance(params, dict):
            params = AnalysisCreate(**params)
        now = utcnow()
        payload = params.parameter_payload()
        workspace_id = self.resolve_workspace_id(user_id, payload.get("workspace_id"))
        payload["workspace_id"] = workspace_id
        with self.connect() as conn:
            cur = conn.execute(
                "insert into analysis_tasks(user_id, workspace_id, status, created_at, updated_at) values (?, ?, 'queued', ?, ?)",
                (user_id, workspace_id, now, now),
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
            for memory_id in self._validate_memory_ids(conn, user_id, payload.get("memory_ids", []), workspace_id):
                conn.execute(
                    "insert into analysis_memory_attachments(analysis_task_id, memory_id, created_at) values (?, ?, ?)",
                    (task_id, memory_id, now),
                )
        return self.get_task_for_user(task_id, user_id, include_detail=False)  # type: ignore[return-value]


    def get_task_owner_id(self, task_id: int) -> int | None:
        with self.connect() as conn:
            row = conn.execute("select user_id from analysis_tasks where id = ?", (task_id,)).fetchone()
            return int(row["user_id"]) if row else None

    def get_task_workspace_id(self, task_id: int) -> int | None:
        with self.connect() as conn:
            row = conn.execute("select workspace_id from analysis_tasks where id = ?", (task_id,)).fetchone()
            return int(row["workspace_id"]) if row and row["workspace_id"] is not None else None

    def count_analysis_tasks(self, *, user_id: int | None = None, workspace_id: int | None = None) -> int:
        clauses: list[str] = []
        values: list[Any] = []
        if user_id is not None:
            clauses.append("user_id = ?")
            values.append(user_id)
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            values.append(workspace_id)
        where = f"where {' and '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            return int(conn.execute(f"select count(*) from analysis_tasks {where}", tuple(values)).fetchone()[0])

    def update_task_status(self, task_id: int, status: str, error: str | None = None) -> None:
        completed_at = utcnow() if status in {"completed", "failed"} else None
        with self.connect() as conn:
            conn.execute(
                "update analysis_tasks set status = ?, updated_at = ?, completed_at = coalesce(?, completed_at), error = ? where id = ?",
                (status, utcnow(), completed_at, error, task_id),
            )

    def fail_interrupted_active_tasks(self, *, reason: str = "analysis interrupted by server restart") -> int:
        now = utcnow()
        active_statuses = ("running", "pending")
        with self.connect() as conn:
            rows = conn.execute(
                """
                select id
                from analysis_tasks
                where status in (?, ?)
                order by id asc
                """,
                active_statuses,
            ).fetchall()
            for row in rows:
                task_id = int(row["id"])
                current = conn.execute("select coalesce(max(sequence), 0) from agent_event_logs where task_id = ?", (task_id,)).fetchone()[0]
                conn.execute(
                    """
                    insert into agent_event_logs(task_id, sequence, agent, event_type, message, payload_json, created_at)
                    values (?, ?, 'System', 'task.failed', ?, ?, ?)
                    """,
                    (task_id, int(current) + 1, reason, json.dumps({"reason": reason, "recovered_on_startup": True}), now),
                )
                conn.execute(
                    "update analysis_tasks set status = 'failed', updated_at = ?, completed_at = ?, error = ? where id = ?",
                    (now, now, reason, task_id),
                )
        return len(rows)

    def list_queued_analysis_tasks(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                select t.id, t.user_id, p.payload_json
                from analysis_tasks t
                join task_parameters p on p.task_id = t.id
                where t.status = 'queued'
                order by t.created_at asc, t.id asc
                """
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "user_id": int(row["user_id"]),
                "parameters": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def get_task_status(self, task_id: int) -> str | None:
        with self.connect() as conn:
            row = conn.execute("select status from analysis_tasks where id = ?", (task_id,)).fetchone()
            return str(row["status"]) if row else None

    def cancel_task_for_user(self, task_id: int, user_id: int, *, reason: str = "cancelled by user") -> dict[str, Any] | None:
        now = utcnow()
        with self.connect() as conn:
            task = conn.execute(
                """
                select * from analysis_tasks t
                where t.id = ? and (
                    t.user_id = ?
                    or exists (select 1 from workspace_members wm where wm.workspace_id = t.workspace_id and wm.user_id = ?)
                )
                """,
                (task_id, user_id, user_id),
            ).fetchone()
            if not task or task["status"] not in {"queued", "running", "pending"}:
                return None
            conn.execute(
                "update analysis_tasks set status = 'cancelled', updated_at = ?, completed_at = ?, error = ? where id = ?",
                (now, now, reason, task_id),
            )
            current = conn.execute("select coalesce(max(sequence), 0) from agent_event_logs where task_id = ?", (task_id,)).fetchone()[0]
            conn.execute(
                """
                insert into agent_event_logs(task_id, sequence, agent, event_type, message, payload_json, created_at)
                values (?, ?, 'System', 'task.cancelled', ?, ?, ?)
                """,
                (task_id, int(current) + 1, reason, json.dumps({"reason": reason}), now),
            )
        return self.get_task_for_user(task_id, user_id)

    def pause_task_for_user(self, task_id: int, user_id: int, *, reason: str = "paused by user") -> dict[str, Any] | None:
        now = utcnow()
        with self.connect() as conn:
            task = conn.execute(
                """
                select * from analysis_tasks t
                where t.id = ? and (
                    t.user_id = ?
                    or exists (select 1 from workspace_members wm where wm.workspace_id = t.workspace_id and wm.user_id = ?)
                )
                """,
                (task_id, user_id, user_id),
            ).fetchone()
            if not task or task["status"] not in {"queued", "running", "pending"}:
                return None
            conn.execute(
                "update analysis_tasks set status = 'paused', updated_at = ?, error = ? where id = ?",
                (now, reason, task_id),
            )
            current = conn.execute("select coalesce(max(sequence), 0) from agent_event_logs where task_id = ?", (task_id,)).fetchone()[0]
            conn.execute(
                """
                insert into agent_event_logs(task_id, sequence, agent, event_type, message, payload_json, created_at)
                values (?, ?, 'System', 'task.paused', ?, ?, ?)
                """,
                (task_id, int(current) + 1, reason, json.dumps({"reason": reason}), now),
            )
        return self.get_task_for_user(task_id, user_id)

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

    def list_tasks_for_user(self, user_id: int, workspace_id: int | None = None) -> list[dict[str, Any]]:
        clauses = ["(t.user_id = ? or exists (select 1 from workspace_members wm where wm.workspace_id = t.workspace_id and wm.user_id = ?))"]
        values: list[Any] = [user_id, user_id]
        if workspace_id is not None:
            clauses.append("t.workspace_id = ?")
            values.append(workspace_id)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                select t.*, p.ticker, p.analysis_date, p.payload_json, fd.decision, le.last_event_at
                from analysis_tasks t
                join task_parameters p on p.task_id = t.id
                left join final_decisions fd on fd.task_id = t.id
                left join (
                    select task_id, max(created_at) as last_event_at
                    from agent_event_logs
                    group by task_id
                ) le on le.task_id = t.id
                where {' and '.join(clauses)}
                order by t.created_at desc, t.id desc
                """,
                tuple(values),
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            payload_json = item.pop("payload_json", None)
            item["parameters"] = json.loads(payload_json) if payload_json else None
            item["ticker_name"] = item["parameters"].get("ticker_name") if item["parameters"] else None
            items.append(item)
        return items

    def export_user_data(self, user_id: int, workspace_id: int | None = None) -> dict[str, Any]:
        analyses = [self.get_task_for_user(task["id"], user_id) for task in self.list_tasks_for_user(user_id, workspace_id)]
        interventions = [self.get_intervention_for_user(session["id"], user_id) for session in self.list_interventions_for_user(user_id, workspace_id)]
        schedules = [self.get_schedule_for_user(schedule["id"], user_id) for schedule in self.list_schedules_for_user(user_id, workspace_id)]
        workspace = self.get_workspace_for_user(workspace_id, user_id) if workspace_id is not None else None
        return {
            "format": "tradingagents.web.export.v1",
            "exported_at": utcnow(),
            "workspace": workspace,
            "analyses": [item for item in analyses if item],
            "memories": self.list_memories_for_user(user_id, archived=None, workspace_id=workspace_id),
            "schedules": [item for item in schedules if item],
            "interventions": [item for item in interventions if item],
        }

    def export_workspace_compliance(self, *, workspace_id: int, requester_user_id: int) -> dict[str, Any]:
        workspace = self.get_workspace_for_user(workspace_id, requester_user_id)
        usage_ledger = self.list_usage_ledger(workspace_id=workspace_id)
        audit_logs = self.list_audit_logs_for_workspace(workspace_id)
        retention_decisions = [item for item in audit_logs if item["event_type"].startswith("retention.")]
        return {
            "format": "tradingagents.web.compliance.v1",
            "exported_at": utcnow(),
            "workspace": workspace,
            "audit_logs": audit_logs,
            "identity_mappings": self.list_identity_links(workspace_id=workspace_id),
            "retention_decisions": retention_decisions,
            "usage_ledger": usage_ledger,
            "legal_holds": self.list_legal_holds(workspace_id=workspace_id),
            "provisioning_events": self.list_provisioning_events(workspace_id=workspace_id),
        }

    def get_task_for_user(self, task_id: int, user_id: int, *, include_detail: bool = True) -> dict[str, Any] | None:
        with self.connect() as conn:
            task = conn.execute(
                """
                select * from analysis_tasks t
                where t.id = ? and (
                    t.user_id = ?
                    or exists (select 1 from workspace_members wm where wm.workspace_id = t.workspace_id and wm.user_id = ?)
                )
                """,
                (task_id, user_id, user_id),
            ).fetchone()
            if not task:
                return None
            params = conn.execute("select * from task_parameters where task_id = ?", (task_id,)).fetchone()
            last_event = conn.execute("select max(created_at) as last_event_at from agent_event_logs where task_id = ?", (task_id,)).fetchone()
            result = dict(task)
            result["last_event_at"] = last_event["last_event_at"] if last_event else None
            if params:
                payload = json.loads(params["payload_json"])
                result["parameters"] = payload
                result["ticker"] = params["ticker"]
                result["analysis_date"] = params["analysis_date"]
                result["ticker_name"] = payload.get("ticker_name")
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
            cur = conn.execute(
                """
                delete from analysis_tasks
                where id = ? and (
                    user_id = ?
                    or workspace_id in (select workspace_id from workspace_members where user_id = ? and role in ('owner', 'admin'))
                )
                """,
                (task_id, user_id, user_id),
            )
            return cur.rowcount > 0


    def create_schedule(self, user_id: int, payload: ScheduledAnalysisCreate) -> dict[str, Any]:
        now = utcnow()
        start_at = self._format_datetime(payload.start_at)
        workspace_id = self.resolve_workspace_id(user_id, payload.workspace_id)
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into schedules(
                    user_id, workspace_id, name, status, ticker, start_at, next_run_at, interval, analysts_json,
                    research_depth, llm_provider, backend_url, quick_model, deep_model, output_language,
                    analysis_date, analysis_date_policy, google_thinking_level, openai_reasoning_effort,
                    anthropic_effort, created_at, updated_at
                ) values (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    workspace_id,
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

    def list_schedules_for_user(self, user_id: int, workspace_id: int | None = None) -> list[dict[str, Any]]:
        clauses = ["deleted_at is null", "(user_id = ? or workspace_id in (select workspace_id from workspace_members where user_id = ?))"]
        values: list[Any] = [user_id, user_id]
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            values.append(workspace_id)
        with self.connect() as conn:
            rows = conn.execute(
                f"select * from schedules where {' and '.join(clauses)} order by created_at desc, id desc",
                tuple(values),
            ).fetchall()
        return [self._schedule_dict(row) for row in rows]

    def get_schedule_for_user(self, schedule_id: int, user_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                select * from schedules
                where id = ? and deleted_at is null and (
                    user_id = ? or workspace_id in (select workspace_id from workspace_members where user_id = ?)
                )
                """,
                (schedule_id, user_id, user_id),
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
            if key in {"memory_ids", "workspace_id"}:
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
        values.extend([schedule_id, user_id, user_id])
        with self.connect() as conn:
            conn.execute(
                f"""
                update schedules set {', '.join(fields)}
                where id = ? and deleted_at is null and (
                    user_id = ? or workspace_id in (select workspace_id from workspace_members where user_id = ? and role in ('owner', 'admin', 'member'))
                )
                """,
                tuple(values),
            )
        if payload.memory_ids is not None:
            self.replace_schedule_memory_attachments(schedule_id, user_id, payload.memory_ids)
        return self.get_schedule_for_user(schedule_id, user_id)

    def set_schedule_status(self, schedule_id: int, user_id: int, status: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute(
                """
                update schedules set status = ?, updated_at = ?
                where id = ? and deleted_at is null and (
                    user_id = ? or workspace_id in (select workspace_id from workspace_members where user_id = ? and role in ('owner', 'admin', 'member'))
                )
                """,
                (status, utcnow(), schedule_id, user_id, user_id),
            )
        return self.get_schedule_for_user(schedule_id, user_id)

    def delete_schedule(self, schedule_id: int, user_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                """
                update schedules set deleted_at = ?, updated_at = ?
                where id = ? and deleted_at is null and (
                    user_id = ? or workspace_id in (select workspace_id from workspace_members where user_id = ? and role in ('owner', 'admin'))
                )
                """,
                (utcnow(), utcnow(), schedule_id, user_id, user_id),
            )
            return cur.rowcount > 0

    def list_due_schedules_for_user(self, user_id: int, now: str, workspace_id: int | None = None) -> list[dict[str, Any]]:
        clauses = [
            "(user_id = ? or workspace_id in (select workspace_id from workspace_members where user_id = ? and role in ('owner', 'admin', 'member')))",
            "status = 'active'",
            "deleted_at is null",
            "next_run_at <= ?",
        ]
        values: list[Any] = [user_id, user_id, now]
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            values.append(workspace_id)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                select * from schedules
                where {' and '.join(clauses)}
                order by next_run_at asc, id asc
                """,
                tuple(values),
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

    def update_schedule_execution_task(self, execution_id: int, analysis_task_id: int, status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "update schedule_executions set analysis_task_id = ?, status = ? where id = ?",
                (analysis_task_id, status, execution_id),
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


    def _validate_memory_ids(self, conn: sqlite3.Connection, user_id: int, memory_ids: list[int], workspace_id: int) -> list[int]:
        if not memory_ids:
            return []
        unique_ids = list(dict.fromkeys(int(memory_id) for memory_id in memory_ids))
        placeholders = ",".join("?" for _ in unique_ids)
        rows = conn.execute(
            f"""
            select id from agent_memories
            where archived = 0 and workspace_id = ? and id in ({placeholders})
              and (user_id = ? or workspace_id in (select workspace_id from workspace_members where user_id = ?))
            """,
            (workspace_id, *unique_ids, user_id, user_id),
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
        workspace_id = int(params.get("workspace_id") or self.get_personal_workspace_id(user_id))
        with self.connect() as conn:
            for section, agent_name in section_agents.items():
                content = (sections.get(section) or "").strip()
                if not content:
                    continue
                conn.execute(
                    """
                    insert into agent_memories(
                        user_id, workspace_id, source_analysis_task_id, ticker, analysis_date, agent_name, title, content, tags_json, archived, created_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        user_id,
                        workspace_id,
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
        workspace_id: int | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["(user_id = ? or workspace_id in (select workspace_id from workspace_members where user_id = ?))"]
        values: list[Any] = [user_id, user_id]
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            values.append(workspace_id)
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
            row = conn.execute(
                """
                select * from agent_memories
                where id = ? and (user_id = ? or workspace_id in (select workspace_id from workspace_members where user_id = ?))
                """,
                (memory_id, user_id, user_id),
            ).fetchone()
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
        values.extend([memory_id, user_id, user_id])
        with self.connect() as conn:
            conn.execute(
                f"""
                update agent_memories set {', '.join(fields)}
                where id = ? and (user_id = ? or workspace_id in (select workspace_id from workspace_members where user_id = ? and role in ('owner', 'admin', 'member')))
                """,
                tuple(values),
            )
        return self.get_memory_for_user(memory_id, user_id)

    def set_memory_archived(self, memory_id: int, user_id: int, archived: bool) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute(
                """
                update agent_memories set archived = ?
                where id = ? and (user_id = ? or workspace_id in (select workspace_id from workspace_members where user_id = ? and role in ('owner', 'admin', 'member')))
                """,
                (1 if archived else 0, memory_id, user_id, user_id),
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
            schedule = conn.execute("select workspace_id from schedules where id = ?", (schedule_id,)).fetchone()
            workspace_id = int(schedule["workspace_id"]) if schedule and schedule["workspace_id"] is not None else self.get_personal_workspace_id(user_id)
            valid_ids = self._validate_memory_ids(conn, user_id, memory_ids, workspace_id)
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
        task = self.get_task_for_user(source_analysis_task_id, user_id, include_detail=False)
        if not task:
            return None
        workspace_id = int(task["workspace_id"] or self.get_personal_workspace_id(user_id))
        now = utcnow()
        with self.connect() as conn:
            cur = conn.execute(
                """
                insert into intervention_sessions(user_id, workspace_id, source_analysis_task_id, target_agent_name, status, created_at, updated_at)
                values (?, ?, ?, ?, 'open', ?, ?)
                """,
                (user_id, workspace_id, source_analysis_task_id, target_agent_name, now, now),
            )
        return self.get_intervention_for_user(cur.lastrowid, user_id)

    def list_interventions_for_user(self, user_id: int, workspace_id: int | None = None) -> list[dict[str, Any]]:
        clauses = ["(user_id = ? or workspace_id in (select workspace_id from workspace_members where user_id = ?))"]
        values: list[Any] = [user_id, user_id]
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            values.append(workspace_id)
        with self.connect() as conn:
            rows = conn.execute(
                f"select * from intervention_sessions where {' and '.join(clauses)} order by created_at desc, id desc",
                tuple(values),
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
                """
                select * from intervention_sessions
                where id = ? and (user_id = ? or workspace_id in (select workspace_id from workspace_members where user_id = ?))
                """,
                (session_id, user_id, user_id),
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
            cur = conn.execute(
                """
                delete from intervention_sessions
                where id = ? and (user_id = ? or workspace_id in (select workspace_id from workspace_members where user_id = ? and role in ('owner', 'admin')))
                """,
                (session_id, user_id, user_id),
            )
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
                """
                update intervention_sessions set status = ?, updated_at = ?, closed_at = coalesce(?, closed_at)
                where id = ? and (user_id = ? or workspace_id in (select workspace_id from workspace_members where user_id = ? and role in ('owner', 'admin', 'member')))
                """,
                (status, utcnow(), closed_at, session_id, user_id, user_id),
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

    def _usage_ledger_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["allowed"] = bool(data["allowed"])
        data["metadata"] = json.loads(data.pop("metadata_json"))
        return data

    def _provisioning_event_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json"))
        return data

    def _legal_hold_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["active"] = data.get("released_at") is None
        return data

    def _event_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json"))
        return data
