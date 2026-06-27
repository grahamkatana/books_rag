import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from unittest.mock import patch, MagicMock

import migrate_qdrant as mq

print("--- explicit --collection: migrates only that one, no auto-discovery ---")
fake_source = MagicMock()
fake_dest = MagicMock()
fake_source.count.return_value.count = 100
fake_dest.count.return_value.count = 100

with patch("qdrant_client.QdrantClient", side_effect=[fake_source, fake_dest]), \
     patch("qdrant_client.migrate.migrate") as mock_migrate:
    result = mq.migrate_qdrant(
        source_url="http://localhost:6333", dest_url="https://cloud.example.com:6333",
        dest_api_key="key123", collection="book_library",
    )
assert result == {"book_library": 100}
assert mock_migrate.call_args.kwargs["collection_names"] == ["book_library"]
assert not fake_source.get_collections.called
print("OK")

print("\n--- no --collection: auto-discovers every collection on the source ---")
fake_source2 = MagicMock()
fake_dest2 = MagicMock()
c1, c2 = MagicMock(), MagicMock()
c1.name, c2.name = "book_library", "paper_library"
fake_source2.get_collections.return_value.collections = [c1, c2]
fake_source2.count.return_value.count = 50
fake_dest2.count.return_value.count = 50

with patch("qdrant_client.QdrantClient", side_effect=[fake_source2, fake_dest2]), \
     patch("qdrant_client.migrate.migrate") as mock_migrate2:
    result2 = mq.migrate_qdrant(source_url="http://localhost:6333", dest_url="https://cloud.example.com:6333", dest_api_key="key")
assert set(result2.keys()) == {"book_library", "paper_library"}
assert set(mock_migrate2.call_args.kwargs["collection_names"]) == {"book_library", "paper_library"}
print("OK")

print("\n--- recreate and batch_size flags reach migrate() correctly ---")
fake_source3 = MagicMock()
fake_dest3 = MagicMock()
fake_source3.count.return_value.count = 10
fake_dest3.count.return_value.count = 10
with patch("qdrant_client.QdrantClient", side_effect=[fake_source3, fake_dest3]), \
     patch("qdrant_client.migrate.migrate") as mock_migrate3:
    mq.migrate_qdrant(source_url="x", dest_url="y", dest_api_key="k", collection="c", recreate=True, batch_size=250)
assert mock_migrate3.call_args.kwargs["recreate_on_collision"] is True
assert mock_migrate3.call_args.kwargs["batch_size"] == 250
print("OK")

print("\nAll migrate_qdrant assertions passed.")