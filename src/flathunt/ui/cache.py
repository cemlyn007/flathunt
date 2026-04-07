import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Generic, Iterable, TypeVar

from pydantic import TypeAdapter

logger = logging.getLogger(__name__)

T = TypeVar("T")

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


class ModelCache(Generic[T]):
    def __init__(self, model_cls: Any, db_path: str | Path, ttl: int = 86400):
        """Initialise the cache, creating the SQLite database if it does not exist.

        Args:
            model_cls: The Pydantic-compatible type used to validate cached items.
            db_path: Path to the SQLite database file.
            ttl: Time-to-live for cache entries in seconds. Defaults to 86400 (24 h).
        """
        self.ttl = ttl
        self._adapter: TypeAdapter[T] = TypeAdapter(model_cls)  # type: ignore[arg-type]
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute(_CREATE_TABLE)
        self._conn.execute(_CREATE_INDEX)
        self._conn.commit()
        self._purge_expired()

    def _purge_expired(self) -> None:
        """Delete all entries whose TTL has elapsed."""
        cutoff = time.time() - self.ttl
        self._conn.execute("DELETE FROM cache WHERE timestamp < ?", (cutoff,))
        self._conn.commit()

    def get(self, id: str) -> T:
        """Retrieve a cached item by key, raising if missing or expired.

        Args:
            id: The cache key to look up.

        Returns:
            The cached item of type T.

        Raises:
            KeyError: If the key is not present or the entry has expired.
        """
        cutoff = time.time() - self.ttl
        row = self._conn.execute(
            "SELECT item FROM cache WHERE key = ? AND timestamp >= ?",
            (id, cutoff),
        ).fetchone()
        if row is None:
            raise KeyError(id)
        return self._adapter.validate_json(row[0])

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
