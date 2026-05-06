from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from .database import WebRepository


MIGRATION_TABLES = [
    "users",
    "user_identity_links",
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


def backup_sqlite_database(source: Path | str, destination: Path | str) -> Path:
    source_path = Path(source).expanduser()
    if not source_path.exists():
        raise FileNotFoundError(f"SQLite source database does not exist: {source_path}")
    destination_path = Path(destination).expanduser()
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source_path) as source_conn, sqlite3.connect(destination_path) as destination_conn:
        source_conn.backup(destination_conn)
        integrity = destination_conn.execute("pragma integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise RuntimeError(f"SQLite backup integrity check failed: {integrity[0] if integrity else 'no result'}")
    return destination_path


def _connect_readonly(path: Path | str) -> sqlite3.Connection:
    source_path = Path(path).expanduser()
    if not source_path.exists():
        raise FileNotFoundError(f"SQLite source database does not exist: {source_path}")
    conn = sqlite3.connect(source_path)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    return conn


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row["name"]
        for row in conn.execute("select name from sqlite_master where type = 'table' and name not like 'sqlite_%'").fetchall()
    }


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"select count(*) from {table}").fetchone()[0])


def _backup_status(source: Path | str, backup_path: Path | str | None) -> dict[str, Any]:
    if backup_path is None:
        return {"ok": False, "path": None, "reason": "backup_path is required"}
    backup = Path(backup_path).expanduser()
    if not backup.exists():
        return {"ok": False, "path": str(backup), "reason": "backup does not exist"}
    with sqlite3.connect(backup) as conn:
        integrity = conn.execute("pragma integrity_check").fetchone()
    return {"ok": bool(integrity and integrity[0] == "ok"), "path": str(backup), "integrity": integrity[0] if integrity else None}


def plan_sqlite_to_postgres_migration(source: Path | str, *, backup_path: Path | str | None = None) -> dict[str, Any]:
    """Dry-run a SQLite-to-production-store migration.

    Phase 8 keeps this helper storage-neutral for tests and local runbooks: the source is
    inspected read-only and the returned machine-readable plan is suitable for a later
    apply step against either a Postgres adapter or a SQLite stand-in used by tests.
    """

    source_path = Path(source).expanduser()
    with _connect_readonly(source_path) as conn:
        existing = _table_names(conn)
        tables = {
            table: {
                "exists": table in existing,
                "row_count": _table_count(conn, table) if table in existing else 0,
            }
            for table in MIGRATION_TABLES
        }
    backup = _backup_status(source_path, backup_path)
    return {
        "source": str(source_path),
        "dry_run": True,
        "backup": backup,
        "tables": tables,
        "unsupported": [],
    }


def _copy_table(source_conn: sqlite3.Connection, target_conn: sqlite3.Connection, table: str) -> dict[str, int]:
    source_tables = _table_names(source_conn)
    target_tables = _table_names(target_conn)
    if table not in source_tables or table not in target_tables:
        return {"source_rows": 0, "inserted_rows": 0}
    rows = source_conn.execute(f"select * from {table}").fetchall()
    if not rows:
        return {"source_rows": 0, "inserted_rows": 0}
    columns = rows[0].keys()
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    before = target_conn.total_changes
    for row in rows:
        target_conn.execute(
            f"insert or ignore into {table} ({column_sql}) values ({placeholders})",
            tuple(row[column] for column in columns),
        )
    return {"source_rows": len(rows), "inserted_rows": target_conn.total_changes - before}


def apply_sqlite_to_postgres_migration(
    source: Path | str,
    target: Path | str,
    *,
    backup_path: Path | str | None = None,
    require_backup: bool = True,
) -> dict[str, Any]:
    backup = _backup_status(source, backup_path)
    if require_backup and not backup["ok"]:
        raise RuntimeError(f"Refusing migration without a readable backup: {backup.get('reason') or backup.get('integrity')}")
    source_path = Path(source).expanduser()
    target_path = Path(target).expanduser()
    WebRepository(target_path)
    table_results: dict[str, dict[str, int]] = {}
    with _connect_readonly(source_path) as source_conn, sqlite3.connect(target_path) as target_conn:
        target_conn.row_factory = sqlite3.Row
        target_conn.execute("pragma foreign_keys = on")
        for table in MIGRATION_TABLES:
            table_results[table] = _copy_table(source_conn, target_conn, table)
    return {"applied": True, "source": str(source_path), "target": str(target_path), "backup": backup, "tables": table_results}


def validate_sqlite_to_postgres_migration(source: Path | str, target: Path | str) -> dict[str, Any]:
    source_path = Path(source).expanduser()
    target_path = Path(target).expanduser()
    tables: dict[str, dict[str, Any]] = {}
    ok = True
    with _connect_readonly(source_path) as source_conn, _connect_readonly(target_path) as target_conn:
        source_tables = _table_names(source_conn)
        target_tables = _table_names(target_conn)
        for table in MIGRATION_TABLES:
            source_count = _table_count(source_conn, table) if table in source_tables else 0
            target_count = _table_count(target_conn, table) if table in target_tables else 0
            matches = target_count >= source_count
            ok = ok and matches
            tables[table] = {"source_count": source_count, "target_count": target_count, "matches": matches}
    return {"ok": ok, "source": str(source_path), "target": str(target_path), "tables": tables}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TradingAgents web maintenance helpers")
    subcommands = parser.add_subparsers(dest="command", required=True)
    backup = subcommands.add_parser("backup", help="Create a consistent SQLite backup")
    backup.add_argument("--database", required=True, help="Source SQLite database path")
    backup.add_argument("--output", required=True, help="Destination backup path")
    plan = subcommands.add_parser("migration-plan", help="Dry-run a SQLite-to-Postgres migration plan")
    plan.add_argument("--source", required=True, help="Source SQLite database path")
    plan.add_argument("--backup", help="Recent backup path")
    apply = subcommands.add_parser("migration-apply", help="Apply an idempotent SQLite migration into a target store")
    apply.add_argument("--source", required=True, help="Source SQLite database path")
    apply.add_argument("--target", required=True, help="Target database path or local migration stand-in")
    apply.add_argument("--backup", required=True, help="Recent readable backup path")
    validate = subcommands.add_parser("migration-validate", help="Validate migrated source/target counts")
    validate.add_argument("--source", required=True, help="Source SQLite database path")
    validate.add_argument("--target", required=True, help="Target database path or local migration stand-in")
    args = parser.parse_args(argv)
    if args.command == "backup":
        output = backup_sqlite_database(args.database, args.output)
        print(output)
        return 0
    if args.command == "migration-plan":
        print(json.dumps(plan_sqlite_to_postgres_migration(args.source, backup_path=args.backup), indent=2, sort_keys=True))
        return 0
    if args.command == "migration-apply":
        print(json.dumps(apply_sqlite_to_postgres_migration(args.source, args.target, backup_path=args.backup), indent=2, sort_keys=True))
        return 0
    if args.command == "migration-validate":
        print(json.dumps(validate_sqlite_to_postgres_migration(args.source, args.target), indent=2, sort_keys=True))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
