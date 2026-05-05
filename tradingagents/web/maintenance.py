from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def backup_sqlite_database(source: Path | str, destination: Path | str) -> Path:
    source_path = Path(source).expanduser()
    destination_path = Path(destination).expanduser()
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source_path) as source_conn, sqlite3.connect(destination_path) as destination_conn:
        source_conn.backup(destination_conn)
        destination_conn.execute("pragma integrity_check").fetchone()
    return destination_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TradingAgents web maintenance helpers")
    subcommands = parser.add_subparsers(dest="command", required=True)
    backup = subcommands.add_parser("backup", help="Create a consistent SQLite backup")
    backup.add_argument("--database", required=True, help="Source SQLite database path")
    backup.add_argument("--output", required=True, help="Destination backup path")
    args = parser.parse_args(argv)
    if args.command == "backup":
        output = backup_sqlite_database(args.database, args.output)
        print(output)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
