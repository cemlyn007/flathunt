"""Tests for rightmove_email_matched_ids asset — null-safe commute filter behaviour.

Strategy:
- ``get_properties_journey_duration_cached`` is patched to avoid real TfL HTTP
  calls, using an async generator mock (the same pattern used in
  test_matched_ids.py for zoopla).
- A real ``ModelCache`` backed by a tmp SQLite file is used for the journey cache
  (mirrors project convention of avoiding fake caches).
- ``QueriesResource`` and ``TflResource`` are real Dagster resources constructed
  with explicit values so no env-var lookup occurs.
- ``CacheResource`` is mocked with ``data_dir = str(tmp_path)``.

Core rules under test:
1. Listings without coordinates → emit ``MatchedProperty`` with
   ``commute_durations == []`` (commute-unknown path, NOT discarded).
2. A listing whose duration exceeds the destination max → excluded.
3. A listing within the limit → kept.
4. No destinations configured → all candidates kept with empty durations.
"""

from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import dagster as dg

from flathunt.defs.resources import QueriesResource, TflResource
from flathunt.defs.rightmove_email.matched_ids import rightmove_email_matched_ids
from flathunt.models import FinalProperty, MatchedProperty

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _property(
    prop_id: int = 200001,
    latitude: float | None = 51.5,
    longitude: float | None = -0.1,
) -> FinalProperty:
    """Build a minimal but fully-valid FinalProperty for testing."""
    return FinalProperty(
        id=prop_id,
        display_address="1 Test Street, London",
        latitude=latitude,
        longitude=longitude,
    )


def _make_queries(
    lon: float = -0.1, lat: float = 51.5, max_duration: float = 30.0
) -> QueriesResource:
    return QueriesResource(
        queries=[{"lon": lon, "lat": lat, "max_duration": max_duration}]
    )


def _make_tfl() -> TflResource:
    return TflResource(api_key="fake-api-key")  # type: ignore[call-arg]


def _make_cache_mock(tmp_path: Path) -> MagicMock:
    mock = MagicMock()
    mock.data_dir = str(tmp_path)
    return mock


def _run_asset(
    properties: list[FinalProperty],
    *,
    queries: QueriesResource | None = None,
    tfl: TflResource | None = None,
    tmp_path: Path,
    patch_durations: list[int | None] | None = None,
) -> list[MatchedProperty]:
    """Run the asset with optional journey-duration mocking.

    ``patch_durations`` is a flat list of durations in the same order as
    ``flat_to_froms`` would be built by the asset (property x destination).
    Pass ``None`` items to simulate a failed/unknown journey lookup.

    If ``patch_durations`` is ``None``, the patch is still applied but yields
    nothing (no duration calls expected, e.g. for no-coords properties only).
    """
    if queries is None:
        queries = _make_queries()
    if tfl is None:
        tfl = _make_tfl()
    cache = _make_cache_mock(tmp_path)

    flat = list(patch_durations) if patch_durations is not None else []

    async def mock_gen(*args, **kwargs):  # noqa: RUF029
        for i, d in enumerate(flat):
            yield i, d

    with patch(
        "flathunt.defs.rightmove_email.matched_ids.get_properties_journey_duration_cached",
        new=mock_gen,
    ):
        context = dg.build_asset_context()
        return cast(
            list[MatchedProperty],
            rightmove_email_matched_ids(
                context=context,
                queries=queries,
                tfl_resource=tfl,
                cache=cache,
                rightmove_email_candidate_properties=properties,
            ),
        )


# ---------------------------------------------------------------------------
# Commute-unknown path: properties without coordinates
# ---------------------------------------------------------------------------


class TestNoCoordKeptWithEmptyDurations:
    def test_no_coords_kept_with_empty_durations(self, tmp_path: Path) -> None:
        """A candidate with latitude=None must appear in output with commute_durations=[].

        Missing coordinates mean commute is unknown.  The property must not be
        discarded — it flows downstream as commute-unknown.
        """
        prop = _property(300001, latitude=None, longitude=None)
        result = _run_asset([prop], tmp_path=tmp_path, patch_durations=[])

        ids = [mp.property_id for mp in result]
        assert 300001 in ids, (
            "Property without coordinates must appear in matched output"
        )
        matched = next(mp for mp in result if mp.property_id == 300001)
        assert matched.commute_durations == [], (
            "Property without coordinates must have commute_durations=[]"
        )


# ---------------------------------------------------------------------------
# Commute filter: duration over limit
# ---------------------------------------------------------------------------


class TestKnownDurationOverLimitExcluded:
    def test_known_duration_over_limit_excluded(self, tmp_path: Path) -> None:
        """A property whose commute duration exceeds the destination max is excluded."""
        prop = _property(300002, latitude=51.5, longitude=-0.1)
        queries = _make_queries(max_duration=30.0)
        # Duration 45 minutes > max 30 → must be excluded
        result = _run_asset(
            [prop], queries=queries, tmp_path=tmp_path, patch_durations=[45]
        )

        ids = [mp.property_id for mp in result]
        assert 300002 not in ids, (
            "Property with duration exceeding max must be excluded"
        )


# ---------------------------------------------------------------------------
# Commute filter: duration within limit
# ---------------------------------------------------------------------------


class TestWithinLimitKept:
    def test_within_limit_kept(self, tmp_path: Path) -> None:
        """A property whose commute duration is within the destination max is kept."""
        prop = _property(300003, latitude=51.5, longitude=-0.1)
        queries = _make_queries(max_duration=30.0)
        # Duration 20 minutes < max 30 → must be kept
        result = _run_asset(
            [prop], queries=queries, tmp_path=tmp_path, patch_durations=[20]
        )

        ids = [mp.property_id for mp in result]
        assert 300003 in ids, "Property with duration within max must be kept"
        matched = next(mp for mp in result if mp.property_id == 300003)
        assert matched.commute_durations == [20]


# ---------------------------------------------------------------------------
# No destinations configured: all candidates returned
# ---------------------------------------------------------------------------


class TestNoDestinationsReturnsAll:
    def test_no_destinations_returns_all(self, tmp_path: Path) -> None:
        """When no commute destinations are configured, all candidates are returned.

        Mirrors zoopla_matched_ids early-return behaviour: without destinations
        to evaluate against, every candidate is kept with empty durations.
        """
        queries = QueriesResource(queries=[])
        props = [
            _property(400001, latitude=51.5, longitude=-0.1),
            _property(400002, latitude=None, longitude=None),
        ]
        result = _run_asset(props, queries=queries, tmp_path=tmp_path)

        ids = [mp.property_id for mp in result]
        assert 400001 in ids, "All properties must be returned when no dests configured"
        assert 400002 in ids, "All properties must be returned when no dests configured"
        for mp in result:
            assert mp.commute_durations == [], (
                "All properties must have empty durations when no dests configured"
            )
