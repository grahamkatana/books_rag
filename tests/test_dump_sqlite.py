import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import sqlite3
import shutil
import tempfile

import dump_sqlite as ds

print("--- real dump + replay round trip: data survives exactly ---")
with tempfile.TemporaryDirectory() as tmp:
    src_path = Path(tmp) / "source.db"
    conn = sqlite3.connect(str(src_path))
    conn.execute("CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT, year INTEGER)")
    conn.execute("INSERT INTO widgets (name, year) VALUES ('A Real Widget', 2024)")
    conn.execute("INSERT INTO widgets (name, year) VALUES ('Another One', 2025)")
    conn.commit()
    conn.close()

    out_path = Path(tmp) / "dump.sql"
    statement_count = ds.dump_sqlite(str(src_path), str(out_path))
    assert statement_count > 0
    assert out_path.exists()

    dump_text = out_path.read_text()
    assert "widgets" in dump_text
    assert "A Real Widget" in dump_text

    # Replay into a completely fresh database, the same way a real restore would
    replay_path = Path(tmp) / "replay.db"
    replay_conn = sqlite3.connect(str(replay_path))
    replay_conn.executescript(dump_text)
    replay_conn.commit()

    rows = replay_conn.execute("SELECT name, year FROM widgets ORDER BY id").fetchall()
    assert rows == [("A Real Widget", 2024), ("Another One", 2025)], \
        "data must survive the dump -> replay round trip exactly"
    replay_conn.close()
print("OK")

print("\n--- nonexistent db_path: raises FileNotFoundError cleanly ---")
try:
    ds.dump_sqlite("/tmp/definitely_does_not_exist_12345.db", "/tmp/out.sql")
    raise AssertionError("should have raised FileNotFoundError")
except FileNotFoundError:
    pass
print("OK")

print("\n--- creates parent directories for the output path automatically ---")
with tempfile.TemporaryDirectory() as tmp:
    src_path = Path(tmp) / "source2.db"
    conn = sqlite3.connect(str(src_path))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    nested_out = Path(tmp) / "deep" / "nested" / "path" / "out.sql"
    ds.dump_sqlite(str(src_path), str(nested_out))
    assert nested_out.exists()
print("OK")

print("\nAll dump_sqlite assertions passed.")