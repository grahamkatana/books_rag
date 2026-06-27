"""
Dumps a SQLite database to a portable .sql text file -- the SQL
statements needed to recreate the schema and every row, the same
thing `sqlite3 book_rag.db .dump > backup.sql` produces, but using
Python's own built-in sqlite3 module (iterdump()) rather than shelling
out to the sqlite3 CLI binary, which isn't guaranteed to be installed
or on PATH -- notably on Windows, where it usually isn't unless added
separately. This way the dump works anywhere Python itself runs.

This is a backup/portability tool, not a migration tool: the output
is plain SQL you can replay into a fresh SQLite database later
(`sqlite3 new.db < backup.sql`), inspect by hand, or keep as a
point-in-time snapshot before doing something riskier (a big rerun, an
--force pipeline pass, a schema migration). For an actual
SQLite -> Postgres migration, use migrate_to_cloud.py's own
sqlite-to-postgres command instead -- that copies rows directly
between two live databases, not through an intermediate file.

Usage:
    uv run python scripts/dump_sqlite.py
    uv run python scripts/dump_sqlite.py --db-path book_rag.db --output backups/book_rag_2026-06-27.sql
"""

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def dump_sqlite(db_path: str, output_path: str) -> int:
    """Writes db_path's full .dump output (schema + data, as plain SQL
    statements) to output_path. Returns the number of SQL statements
    written (iterdump() yields one string per statement, and some --
    a CREATE TABLE with several columns -- span multiple physical
    lines each), so a caller -- or this module's own tests -- has
    something concrete to assert on beyond "it didn't raise"."""
    db_file = Path(db_path)
    if not db_file.exists():
        raise FileNotFoundError(f"No SQLite database found at {db_path}")

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_file))
    try:
        statement_count = 0
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"-- Dump of {db_file.resolve()}\n")
            f.write(f"-- Generated {datetime.now(timezone.utc).isoformat()}\n\n")
            for statement in conn.iterdump():
                f.write(statement + "\n")
                statement_count += 1
    finally:
        conn.close()

    return statement_count


def main():
    parser = argparse.ArgumentParser(description="Dump a SQLite database to a portable .sql file.")
    parser.add_argument("--db-path", default="book_rag.db", help="Path to the source SQLite file")
    parser.add_argument("--output", default=None,
                         help="Output .sql file path (default: backups/<db-name>_<timestamp>.sql)")
    args = parser.parse_args()

    output_path = args.output
    if output_path is None:
        db_name = Path(args.db_path).stem
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = f"backups/{db_name}_{timestamp}.sql"

    print(f"Dumping {args.db_path} -> {output_path} ...")
    statement_count = dump_sqlite(args.db_path, output_path)
    print(f"Done. Wrote {statement_count} SQL statement(s) to {output_path}")


if __name__ == "__main__":
    main()