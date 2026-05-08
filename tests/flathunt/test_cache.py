import time

import pytest

from flathunt.cache import ModelCache


@pytest.fixture
def cache(tmp_path):
    return ModelCache(int | None, tmp_path / "test.db")


def test_get_raises_for_missing_key(cache):
    with pytest.raises(KeyError):
        cache.get("missing")


def test_update_and_get_roundtrip(cache):
    cache.update([("a", 42), ("b", None)])
    assert cache.get("a") == 42
    assert cache.get("b") is None


def test_update_does_not_overwrite_existing_key(cache):
    cache.update([("a", 1)])
    cache.update([("a", 99)])
    assert cache.get("a") == 1


def test_expired_entry_raises_key_error(tmp_path):
    cache = ModelCache(int | None, tmp_path / "test.db", ttl=0)
    cache.update([("a", 10)])
    with pytest.raises(KeyError):
        cache.get("a")


def test_peek_returns_item_and_timestamp(cache):
    before = time.time()
    cache.update([("a", 42)])

    value, timestamp = cache.peek("a")

    assert value == 42
    assert timestamp >= before


def test_upsert_overwrites_existing_key(cache):
    cache.update([("a", 1)])
    cache.upsert([("a", 99)])

    assert cache.get("a") == 99
