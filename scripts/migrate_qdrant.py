"""
Copies one or more Qdrant collections (vectors + payloads) from one
Qdrant instance to another, using qdrant-client's own official
migrate() helper -- not a hand-rolled scroll/upsert loop, which would
need to reimplement the batching, retry, and payload-index recreation
migrate() already handles correctly.

The actual point of this: moving from a local Qdrant (development) to
a cloud-hosted one (production), or between any two Qdrant instances
generally -- this script doesn't know or care which is "local" and
which is "cloud", just source and destination.

Usage:
    uv run python scripts/migrate_qdrant.py \\
        --source-url http://localhost:6333 \\
        --dest-url https://xxxxx.cloud.qdrant.io:6333 \\
        --dest-api-key YOUR_CLOUD_API_KEY

    # Migrate just one collection instead of every collection found on the source:
    uv run python scripts/migrate_qdrant.py \\
        --source-url http://localhost:6333 \\
        --dest-url https://xxxxx.cloud.qdrant.io:6333 \\
        --dest-api-key YOUR_CLOUD_API_KEY \\
        --collection book_library
"""

import argparse


def migrate_qdrant(source_url: str, dest_url: str, source_api_key: str | None = None,
                    dest_api_key: str | None = None, collection: str | None = None,
                    recreate: bool = False, batch_size: int = 100) -> dict:
    """The actual migration logic, separated from argument parsing so
    it's directly callable (and testable) without going through argv.
    Returns {collection_name: point_count_on_destination_after}, so a
    caller has something concrete to check beyond "it didn't raise"."""
    from qdrant_client import QdrantClient
    from qdrant_client.migrate import migrate

    print(f"Source: {source_url}")
    print(f"Destination: {dest_url}")

    source = QdrantClient(url=source_url, api_key=source_api_key)
    dest = QdrantClient(url=dest_url, api_key=dest_api_key)

    collections = [collection] if collection else None
    if collections is None:
        collections = [c.name for c in source.get_collections().collections]
        print(f"No --collection given -- migrating all of: {collections}")

    for name in collections:
        count_before = source.count(name).count
        print(f"\n{name}: {count_before} point(s) on source")

    migrate(
        source, dest,
        collection_names=collections,
        recreate_on_collision=recreate,
        batch_size=batch_size,
    )

    results = {}
    for name in collections:
        count_after = dest.count(name).count
        print(f"{name}: {count_after} point(s) now on destination")
        results[name] = count_after

    print("\nDone.")
    return results


def main():
    parser = argparse.ArgumentParser(description="Copy Qdrant collection(s) from one instance to another.")
    parser.add_argument("--source-url", default="http://localhost:6333")
    parser.add_argument("--source-api-key", default=None)
    parser.add_argument("--dest-url", required=True, help="e.g. https://xxxxx.cloud.qdrant.io:6333")
    parser.add_argument("--dest-api-key", required=True)
    parser.add_argument("--collection", default=None,
                         help="Collection to migrate, e.g. book_library. Omit to migrate every collection found on the source.")
    parser.add_argument("--recreate", action="store_true",
                         help="Recreate the collection on the destination if it already exists there")
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()

    migrate_qdrant(
        source_url=args.source_url, dest_url=args.dest_url,
        source_api_key=args.source_api_key, dest_api_key=args.dest_api_key,
        collection=args.collection, recreate=args.recreate, batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()