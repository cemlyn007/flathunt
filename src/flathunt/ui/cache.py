import logging
import time
from pathlib import Path
from typing import Generic, Iterable, TypeVar

from pydantic import BaseModel, TypeAdapter

logger = logging.getLogger(__name__)

T = TypeVar("T")


class _CacheItem[T](BaseModel):
    timestamp: float
    item: T


class ModelCache(Generic[T]):
    def __init__(self, model_cls: type[T], cache_file: str | Path, ttl: int = 86400):
        """Initialise the cache, loading any existing entries from disk.

        Args:
            model_cls: The Pydantic model class used to validate cached items.
            cache_file: Path to the JSON file used for persistent storage.
            ttl: Time-to-live for cache entries in seconds. Defaults to 86400 (24 h).
        """
        self.model_cls = model_cls
        self.cache_file = Path(cache_file)
        self.cache: dict[str, _CacheItem[T]] = {}
        self._adapter = TypeAdapter(dict[str, _CacheItem[model_cls]])  # type: ignore
        self.ttl = ttl
        self._load()

    def _load(self):
        """Load the cache from disk, discarding any expired entries."""
        if self.cache_file.exists():
            try:
                self.cache = self._adapter.validate_json(
                    self.cache_file.read_bytes(), strict=True
                )
                self.cache = {
                    k: v
                    for k, v in self.cache.items()
                    if v.timestamp >= time.time() - self.ttl
                }
                logger.info(
                    f"Loaded {len(self.cache)} {self.model_cls.__name__} items from cache."
                )
            except Exception:
                logger.exception("Failed to load cache.")
                self.cache = {}
        else:
            logger.info(
                f"No cache found for {self.model_cls.__name__}, starting fresh."
            )

    def _save(self):
        """Persist the current in-memory cache to disk."""
        try:
            self.cache_file.write_bytes(self._adapter.dump_json(self.cache))
            logger.info(
                f"Saved {len(self.cache)} {self.model_cls.__name__} items to cache."
            )
        except Exception:
            logger.exception("Failed to save cache.")

    def get(self, id: str) -> T:
        """Retrieve a cached item by key, raising if missing or expired.

        Args:
            id: The cache key to look up.

        Returns:
            The cached item of type T.

        Raises:
            KeyError: If the key is not present or the entry has expired.
        """
        cache = self.cache[id]
        if cache.timestamp < time.time() - self.ttl:
            del self.cache[id]
            self._save()
            raise KeyError(f"Cache item for {id} has expired.")
        return cache.item

    def update(self, iterables: Iterable[tuple[str, T]]):
        """Add new key/value pairs to the cache and persist to disk.

        Existing keys are not overwritten.

        Args:
            iterables: An iterable of (key, value) pairs to insert.
        """
        for key, item in iterables:
            if key in self.cache:
                continue
            self.cache[key] = _CacheItem(timestamp=time.time(), item=item)
        self._save()
