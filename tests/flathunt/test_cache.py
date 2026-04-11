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
