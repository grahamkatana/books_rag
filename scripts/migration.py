"""
Two data migrations in one script, since they're both "move what I have
to somewhere bigger" operations even though the actual mechanics are
unrelated:

  sqlite-to-postgres   copies every row from a local book_rag.db into a
                        Postgres database, in FK-safe order, then fixes
                        Postgres's identity sequences so they don't
                        collide with the migrated IDs on the next insert.

  qdrant-to-cloud      copies a Qdrant collection (vectors + payloads)
                        from one Qdrant instance to another, using
                        qdrant-client's own official migrate() helper --
                        not a hand-rolled scroll/upsert loop.

Usage:
    # 1. Create the schema on the destination Postgres first -- this
    #    script only copies rows, not schema:
    DATABASE_URL=postgresql+psycopg://user:pass@host:5432/dbname uv run alembic upgrade head

    # 2. Then copy the data:
    uv run python migrate_to_cloud.py sqlite-to-postgres \\
        --sqlite-path book_rag.db \\
        --postgres-url postgresql+psycopg://user:pass@host:5432/dbname

    # Vector migration, e.g. local Qdrant -> Qdrant Cloud:
    uv run python migrate_to_cloud.py qdrant-to-cloud \\
        --source-url http://localhost:6333 \\
        --dest-url https://xxxxx.cloud.qdrant.io:6333 \\
        --dest-api-key YOUR_CLOUD_API_KEY
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def cmd_sqlite_to_postgres(args):
    from sqlalchemy import create_engine, MetaData, select, text

    sqlite_url = f"sqlite:///{args.sqlite_path}"
    print(f"Source (SQLite): {sqlite_url}")
    print(f"Destination (Postgres): {args.postgres_url}")

    src_engine = create_engine(sqlite_url)
    dest_engine = create_engine(args.postgres_url)

    # Reflect the destination schema rather than assuming -- this also
    # doubles as a check that you ran `alembic upgrade head` against
    # Postgres before running this, since reflection will come back
    # empty (and the FK-order loop below will just do nothing) if you
    # didn't.
    metadata = MetaData()
    metadata.reflect(bind=dest_engine)

    # Hand-ordered for FK safety rather than relying on reflection's
    # table order, which isn't guaranteed to respect dependencies: a row
    # in "chats" referencing a not-yet-inserted "users" row would fail.
    table_order = ["users", "books", "chats", "messages", "citations"]

    with src_engine.connect() as src_conn, dest_engine.begin() as dest_conn:
        for table_name in table_order:
            if table_name not in metadata.tables:
                print(f"  [skip] {table_name}: not found on destination -- "
                      f"did you run `alembic upgrade head` against Postgres first?")
                continue

            table = metadata.tables[table_name]

            if args.truncate:
                dest_conn.execute(table.delete())

            rows = src_conn.execute(select(table)).mappings().all()
            if not rows:
                print(f"  {table_name}: 0 rows, nothing to copy")
                continue

            dest_conn.execute(table.insert(), [dict(r) for r in rows])
            print(f"  {table_name}: copied {len(rows)} row(s)")

            # Postgres's identity/serial sequence has no idea rows were
            # just inserted with explicit ids -- without this, the next
            # *normal* insert (no explicit id) would collide with one of
            # the ids we just migrated.
            if "id" in table.c:
                dest_conn.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table_name}), 1))"
                ))

    print("\nDone.")


def cmd_qdrant_to_cloud(args):
    from qdrant_client import QdrantClient
    from qdrant_client.migrate import migrate

    print(f"Source: {args.source_url}")
    print(f"Destination: {args.dest_url}")

    source = QdrantClient(url=args.source_url, api_key=args.source_api_key)
    dest = QdrantClient(url=args.dest_url, api_key=args.dest_api_key)

    collections = [args.collection] if args.collection else None
    if collections is None:
        collections = [c.name for c in source.get_collections().collections]
        print(f"No --collection given -- migrating all of: {collections}")

    for name in collections:
        count_before = source.count(name).count
        print(f"\n{name}: {count_before} point(s) on source")

    migrate(
        source, dest,
        collection_names=collections,
        recreate_on_collision=args.recreate,
        batch_size=args.batch_size,
    )

    for name in collections:
        count_after = dest.count(name).count
        print(f"{name}: {count_after} point(s) now on destination")

    print("\nDone.")


def main():
    parser = argparse.ArgumentParser(description="Migrate local data to cloud-hosted Postgres/Qdrant.")
    sub = parser.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("sqlite-to-postgres", help="Copy every row from a local SQLite db into Postgres")
    p1.add_argument("--sqlite-path", default="book_rag.db", help="Path to the source SQLite file")
    p1.add_argument("--postgres-url", required=True,
                    help="e.g. postgresql+psycopg://user:pass@host:5432/dbname")
    p1.add_argument("--truncate", action="store_true",
                    help="Delete existing rows in each destination table before copying (use on a rerun)")
    p1.set_defaults(func=cmd_sqlite_to_postgres)

    p2 = sub.add_parser("qdrant-to-cloud", help="Copy a Qdrant collection to another Qdrant instance")
    p2.add_argument("--source-url", default="http://localhost:6333")
    p2.add_argument("--source-api-key", default=None)
    p2.add_argument("--dest-url", required=True, help="e.g. https://xxxxx.cloud.qdrant.io:6333")
    p2.add_argument("--dest-api-key", required=True)
    p2.add_argument("--collection", default=None,
                    help="Collection to migrate, e.g. book_library. Omit to migrate every collection found on the source.")
    p2.add_argument("--recreate", action="store_true",
                    help="Recreate the collection on the destination if it already exists there")
    p2.add_argument("--batch-size", type=int, default=100)
    p2.set_defaults(func=cmd_qdrant_to_cloud)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()