"""Migrate legacy JSON caches to the SQLite-backed ModelCache."""

import argparse
import json
import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Constants
_TTL = 86400  # must match ModelCache default

_CACHES = [
    "journey_cache",
    "property_locations_cache",
]

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS cache (
    key       TEXT PRIMARY KEY,
    timestamp REAL NOT NULL,
    item      TEXT NOT NULL
)
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_cache_timestamp ON cache (timestamp)
"""


def _migrate(src: Path, dst: Path) -> None:
    """Migrate a single JSON cache file to SQLite format.

    Args:
        src: Path to the source JSON cache file.
        dst: Path to the destination SQLite cache file.
    """
    if not src.exists():
        logger.info("Skipping %s: file not found.", src.name)
        return

    raw: dict[str, dict] = json.loads(src.read_text())

    cutoff = time.time() - _TTL
    rows = []
    skipped = 0
    for key, entry in raw.items():
        timestamp: float = entry["timestamp"]
        if timestamp < cutoff:
            skipped += 1
            continue
        rows.append((key, timestamp, json.dumps(entry["item"])))

    conn = sqlite3.connect(str(dst))
    conn.execute(_CREATE_TABLE)
    conn.execute(_CREATE_INDEX)
    conn.executemany(
        "INSERT OR IGNORE INTO cache (key, timestamp, item) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()

    logger.info(
        "Migrated %d entries to %s (%d expired entries skipped).",
        len(rows),
        dst,
        skipped,
    )


def main() -> None:
    """Parse arguments and migrate all cache files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "data_dir",
        type=Path,
        help="Directory containing the JSON cache files.",
    )
    args = parser.parse_args()
    data_dir: Path = args.data_dir

    for name in _CACHES:
        _migrate(data_dir / f"{name}.json", data_dir / f"{name}.db")


if __name__ == "__main__":
    main()
