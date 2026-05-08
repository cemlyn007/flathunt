import logging
import sqlite3
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

logger = logging.getLogger(__name__)

# SQL schema constants
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS cache (
    key       TEXT PRIMARY KEY,
    timestamp REAL NOT NULL,
    item      TEXT NOT NULL
)
"""

CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_cache_timestamp ON cache (timestamp)
"""


class ModelCache[T]:
    """Generic cache for Pydantic-compatible models using SQLite backend."""

    def __init__(self, model_cls: Any, db_path: str | Path, ttl: int | None = 86400):
        """Initialise the cache, creating the SQLite database if it does not exist.

        Args:
            model_cls: The Pydantic-compatible type used to validate cached items.
            db_path: Path to the SQLite database file.
            ttl: Time-to-live for cache entries in seconds. Defaults to 86400 (24 h).
                Set to None to disable expiry.
        """
        self.ttl = ttl
        self._adapter: TypeAdapter[T] = TypeAdapter(model_cls)  # type: ignore[arg-type]
        db_path = Path(db_path)
        if not db_path.parent.exists():
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute(CREATE_TABLE)
        self._conn.execute(CREATE_INDEX)
        self._conn.commit()
        self._purge_expired()

    def _get_row(
        self, id: str, *, min_timestamp: float | None = None
    ) -> tuple[float, str]:
        if min_timestamp is None:
            row = self._conn.execute(
                "SELECT timestamp, item FROM cache WHERE key = ?",
                (id,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT timestamp, item FROM cache WHERE key = ? AND timestamp >= ?",
                (id, min_timestamp),
            ).fetchone()
        if row is None:
            raise KeyError(id)
        return float(row[0]), str(row[1])

    def _purge_expired(self) -> None:
        """Delete all entries whose TTL has elapsed."""
        if self.ttl is None:
            return
        cutoff = time.time() - self.ttl
        self._conn.execute("DELETE FROM cache WHERE timestamp < ?", (cutoff,))
        self._conn.commit()

    # Public API
    def get(self, id: str) -> T:
        """Retrieve a cached item by key, raising if missing or expired.

        Args:
            id: The cache key to look up.

        Returns:
            The cached item of type T.

        Raises:
            KeyError: If the key is not present or the entry has expired.
        """
        min_timestamp = None if self.ttl is None else time.time() - self.ttl
        _, item = self._get_row(id, min_timestamp=min_timestamp)
        return self._adapter.validate_json(item)

    def peek(self, id: str) -> tuple[T, float]:
        """Retrieve a cached item and its timestamp without applying TTL checks.

        Args:
            id: The cache key to look up.

        Returns:
            A ``(item, timestamp)`` tuple where ``timestamp`` is the Unix time at
            which the item was last written.

        Raises:
            KeyError: If the key is not present.
        """
        timestamp, item = self._get_row(id)
        return self._adapter.validate_json(item), timestamp

    def update(self, iterables: Iterable[tuple[str, T]]) -> None:
        """Add new key/value pairs to the cache.

        Existing keys are not overwritten.

        Args:
            iterables: An iterable of (key, value) pairs to insert.
        """
        now = time.time()
        self._conn.executemany(
            "INSERT OR IGNORE INTO cache (key, timestamp, item) VALUES (?, ?, ?)",
            [
                (key, now, self._adapter.dump_json(item).decode())
                for key, item in iterables
            ],
        )
        self._conn.commit()

    def upsert(self, iterables: Iterable[tuple[str, T]]) -> None:
        """Insert or replace cached key/value pairs with a fresh timestamp."""
        self._purge_expired()
        now = time.time()
        self._conn.executemany(
            """
            INSERT INTO cache (key, timestamp, item) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                timestamp = excluded.timestamp,
                item = excluded.item
            """,
            [
                (key, now, self._adapter.dump_json(item).decode())
                for key, item in iterables
            ],
        )
        """Delete all entries whose TTL has elapsed."""
        if self.ttl is None:
            return
        cutoff = time.time() - self.ttl
        self._conn.execute("DELETE FROM cache WHERE timestamp < ?", (cutoff,))
        self._conn.commit()
