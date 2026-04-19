import asyncio
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest
from shapely.geometry import box as shapely_box

import rightmove.api as rm_api
import rightmove.models
from flathunt.cache import ModelCache
from flathunt.coords import CommuteDest, LatLon
from flathunt.filters import (
    filter_by_commute,
    filter_properties_by_budget_and_features,
)
from flathunt.property_search import (
    get_commute_durations,
    get_property_ids_in_area_cached,
)
from flathunt.search_utils import get_property_ids_in_area

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_property(
    *,
    id: int = 1,
    longitude: float = -0.1,
    latitude: float = 51.5,
    property_url: str | None = "/property/123",
    price_amount: int = 2000,
    price_frequency: str = "monthly",
    number_of_images: int = 3,
    number_of_floorplans: int = 1,
    display_size: str | None = None,
) -> rightmove.models.MapProperty:
    return rightmove.models.MapProperty.model_construct(
        id=id,
        location=rightmove.models.Location.model_construct(
            longitude=longitude, latitude=latitude
        ),
        property_url=property_url,
        price=rightmove.models.Price.model_construct(
            amount=price_amount, frequency=price_frequency
        ),
        number_of_images=number_of_images,
        number_of_floorplans=number_of_floorplans,
        display_size=display_size,
        display_address="1 Test Street",
    )


# ---------------------------------------------------------------------------
# filter_by_commute
# ---------------------------------------------------------------------------


def test_filter_by_commute_all_pass():
    props = [make_property(id=1), make_property(id=2)]
    durations = [[10, 15], [20, 25]]
    queries = [CommuteDest(-0.1, 51.5, 30), CommuteDest(-0.2, 51.6, 30)]
    result = filter_by_commute(props, durations, queries)
    assert [p for p, _ in result] == props


def test_filter_by_commute_excludes_over_limit():
    prop_ok = make_property(id=1)
    prop_slow = make_property(id=2)
    durations = [[10, 15], [10, 35]]  # prop_slow exceeds second query limit of 30
    queries = [CommuteDest(-0.1, 51.5, 30), CommuteDest(-0.2, 51.6, 30)]
    result = filter_by_commute([prop_ok, prop_slow], durations, queries)
    assert [p for p, _ in result] == [prop_ok]


def test_filter_by_commute_excludes_none_duration():
    prop = make_property(id=1)
    durations = [[None, 15]]
    queries = [CommuteDest(-0.1, 51.5, 30), CommuteDest(-0.2, 51.6, 30)]
    result = filter_by_commute([prop], durations, queries)
    assert result == []


def test_filter_by_commute_empty_properties():
    result = filter_by_commute([], [], [CommuteDest(-0.1, 51.5, 30)])
    assert result == []


def test_filter_by_commute_returns_durations_alongside_properties():
    prop = make_property(id=1)
    durations = [[10, 20]]
    queries = [CommuteDest(-0.1, 51.5, 30), CommuteDest(-0.2, 51.6, 30)]
    result = filter_by_commute([prop], durations, queries)
    assert len(result) == 1
    returned_prop, returned_durations = result[0]
    assert returned_prop is prop
    assert returned_durations == [10, 20]


def test_filter_by_commute_mismatched_properties_and_durations_raises():
    props = [make_property(id=1), make_property(id=2)]
    durations = [[10, 15]]  # only one entry for two properties
    queries = [CommuteDest(-0.1, 51.5, 30)]
    with pytest.raises(ValueError):
        filter_by_commute(props, durations, queries)


def test_filter_by_commute_mismatched_durations_and_queries_raises():
    prop = make_property(id=1)
    durations = [[10]]  # one duration for two queries
    queries = [CommuteDest(-0.1, 51.5, 30), CommuteDest(-0.2, 51.6, 30)]
    with pytest.raises(ValueError):
        filter_by_commute([prop], durations, queries)


# ---------------------------------------------------------------------------
# get_commute_durations
# ---------------------------------------------------------------------------


def test_get_commute_durations_reshapes_flat_to_2d():
    props = [
        make_property(id=1, longitude=-0.1, latitude=51.5),
        make_property(id=2, longitude=-0.2, latitude=51.6),
    ]
    queries = [CommuteDest(-0.3, 51.7, 30), CommuteDest(-0.4, 51.8, 30)]

    # Flat order: prop0->q0, prop0->q1, prop1->q0, prop1->q1
    flat_durations = [10, 20, 30, 40]

    async def mock_gen(*args, **kwargs):  # noqa: RUF029
        for i, d in enumerate(flat_durations):
            yield i, d

    with patch(
        "flathunt.property_search.get_properties_journey_duration_cached",
        new=mock_gen,
    ):
        result = asyncio.run(
            get_commute_durations(
                props, queries, cache=create_autospec(ModelCache), tfl_api_key="key"
            )
        )

    assert result == [[10, 20], [30, 40]]


def test_get_commute_durations_single_property_single_query():
    prop = make_property(id=1, longitude=-0.1, latitude=51.5)
    queries = [CommuteDest(-0.2, 51.6, 30)]

    async def mock_gen(*args, **kwargs):  # noqa: RUF029
        yield 0, 15

    with patch(
        "flathunt.property_search.get_properties_journey_duration_cached",
        new=mock_gen,
    ):
        result = asyncio.run(
            get_commute_durations(
                [prop], queries, cache=create_autospec(ModelCache), tfl_api_key="key"
            )
        )

    assert result == [[15]]


def test_get_commute_durations_empty_properties():
    async def mock_gen(*args, **kwargs):  # noqa: RUF029
        return
        yield  # make it an async generator

    with patch(
        "flathunt.property_search.get_properties_journey_duration_cached",
        new=mock_gen,
    ):
        result = asyncio.run(
            get_commute_durations(
                [],
                [CommuteDest(-0.1, 51.5, 30)],
                cache=create_autospec(ModelCache),
                tfl_api_key="key",
            )
        )

    assert result == []


def test_get_commute_durations_passes_correct_to_froms():
    prop = make_property(id=1, longitude=-0.1, latitude=51.5)
    queries = [CommuteDest(-0.2, 51.6, 30)]

    captured = []

    async def mock_gen(to_froms, cache, tfl_api_key):  # noqa: RUF029
        captured.extend(to_froms)
        yield 0, 10

    with patch(
        "flathunt.property_search.get_properties_journey_duration_cached",
        new=mock_gen,
    ):
        asyncio.run(
            get_commute_durations(
                [prop], queries, cache=create_autospec(ModelCache), tfl_api_key="key"
            )
        )

    assert captured == [(-0.1, 51.5, -0.2, 51.6)]


# ---------------------------------------------------------------------------
# filter_properties_by_budget_and_features
# ---------------------------------------------------------------------------


def test_filter_budget_rent_in_range():
    prop = make_property(price_amount=2000, price_frequency="monthly")
    result = filter_properties_by_budget_and_features(
        [prop], 1500, 2500, False, False, 0, "RENT"
    )
    assert result == [prop]


def test_filter_budget_rent_below_min_excluded():
    prop = make_property(price_amount=1000, price_frequency="monthly")
    result = filter_properties_by_budget_and_features(
        [prop], 1500, 2500, False, False, 0, "RENT"
    )
    assert result == []


def test_filter_budget_rent_above_max_excluded():
    prop = make_property(price_amount=3000, price_frequency="monthly")
    result = filter_properties_by_budget_and_features(
        [prop], 1500, 2500, False, False, 0, "RENT"
    )
    assert result == []


def test_filter_budget_buy_uses_amount_directly():
    prop = make_property(price_amount=500000, price_frequency="monthly")
    result = filter_properties_by_budget_and_features(
        [prop], 400000, 600000, False, False, 0, "BUY"
    )
    assert result == [prop]


def test_filter_requires_floorplan_when_enabled():
    prop_with = make_property(id=1, number_of_floorplans=1)
    prop_without = make_property(id=2, number_of_floorplans=0)
    result = filter_properties_by_budget_and_features(
        [prop_with, prop_without], 0, 99999, True, False, 0, "RENT"
    )
    assert result == [prop_with]


def test_filter_floorplan_not_required_passes_both():
    prop_with = make_property(id=1, number_of_floorplans=1)
    prop_without = make_property(id=2, number_of_floorplans=0)
    result = filter_properties_by_budget_and_features(
        [prop_with, prop_without], 0, 99999, False, False, 0, "RENT"
    )
    assert result == [prop_with, prop_without]


def test_filter_requires_images_when_enabled():
    prop_with = make_property(id=1, number_of_images=3)
    prop_without = make_property(id=2, number_of_images=1)
    result = filter_properties_by_budget_and_features(
        [prop_with, prop_without], 0, 99999, False, True, 0, "RENT"
    )
    assert result == [prop_with]


def test_filter_excludes_property_without_url():
    prop = make_property(property_url=None)  # pyright: ignore[reportArgumentType]
    result = filter_properties_by_budget_and_features(
        [prop], 0, 99999, False, False, 0, "RENT"
    )
    assert result == []


def test_filter_size_sqm_below_minimum_excluded():
    prop = make_property(display_size="45 sqm")
    result = filter_properties_by_budget_and_features(
        [prop], 0, 99999, False, False, 50, "RENT"
    )
    assert result == []


def test_filter_size_sqm_above_minimum_passes():
    prop = make_property(display_size="60 sqm")
    result = filter_properties_by_budget_and_features(
        [prop], 0, 99999, False, False, 50, "RENT"
    )
    assert result == [prop]


def test_filter_size_sqft_converted_and_filtered():
    # 500 sq ft ≈ 46 sqm, below threshold of 50
    prop = make_property(display_size="500 sq. ft.")
    result = filter_properties_by_budget_and_features(
        [prop], 0, 99999, False, False, 50, "RENT"
    )
    assert result == []


def test_filter_no_display_size_passes():
    prop = make_property(display_size=None)
    result = filter_properties_by_budget_and_features(
        [prop], 0, 99999, False, False, 50, "RENT"
    )
    assert result == [prop]


# ---------------------------------------------------------------------------
# get_property_ids_in_area — predicate and early-exit
# ---------------------------------------------------------------------------


def _make_coords():
    """Return a minimal 5-point WGS84 tile polygon."""
    return [
        LatLon(lat=51.50, lon=-0.14),
        LatLon(lat=51.52, lon=-0.14),
        LatLon(lat=51.52, lon=-0.12),
        LatLon(lat=51.50, lon=-0.12),
        LatLon(lat=51.50, lon=-0.14),
    ]


async def test_get_property_ids_in_area_predicate_filters_results():
    """Predicate should exclude properties that do not satisfy it."""
    coords = _make_coords()
    prop_pass = make_property(id=1, number_of_images=5)
    prop_fail = make_property(id=2, number_of_images=1)

    with patch(
        "flathunt.search_utils.rightmove.api.Rightmove.search_incremental",
        new=AsyncMock(return_value=([prop_pass, prop_fail], 2, False)),
    ):
        semaphore = asyncio.Semaphore(1)
        result = await get_property_ids_in_area(
            coords,
            channel="RENT",
            semaphore=semaphore,
            predicate=lambda p: (p.number_of_images or 0) > 2,
        )

    assert result == [prop_pass]


async def test_get_property_ids_in_area_no_predicate_returns_all():
    coords = _make_coords()
    props = [make_property(id=1), make_property(id=2)]

    with patch(
        "flathunt.search_utils.rightmove.api.Rightmove.search_incremental",
        new=AsyncMock(return_value=(props, 2, False)),
    ):
        semaphore = asyncio.Semaphore(1)
        result = await get_property_ids_in_area(
            coords, channel="RENT", semaphore=semaphore
        )

    assert result == props


async def test_get_property_ids_in_area_stopped_early_skips_subdivision():
    """When stopped_early=True the subdivision threshold is not checked."""
    coords = _make_coords()

    # total_count > SEARCH_LIST_MAX_RESULTS but stopped_early → no subdivision
    props = [make_property(id=i) for i in range(5)]

    with patch(
        "flathunt.search_utils.rightmove.api.Rightmove.search_incremental",
        new=AsyncMock(return_value=(props, rm_api.SEARCH_LIST_MAX_RESULTS + 1, True)),
    ):
        semaphore = asyncio.Semaphore(1)
        result = await get_property_ids_in_area(
            coords, channel="RENT", semaphore=semaphore
        )

    assert result == props


# ---------------------------------------------------------------------------
# get_property_ids_in_area_cached — predicate applied to cache hits
# ---------------------------------------------------------------------------


async def test_get_property_ids_in_area_cached_predicate_on_cache_hit():
    """Predicate must be applied to properties returned from the tile cache."""
    prop_pass = make_property(
        id=10, longitude=-0.13, latitude=51.51, number_of_images=5
    )
    prop_fail = make_property(
        id=11, longitude=-0.13, latitude=51.51, number_of_images=1
    )

    bounding_poly = shapely_box(-0.14, 51.50, -0.12, 51.52)
    tile_coords = [
        LatLon(lat=51.50, lon=-0.14),
        LatLon(lat=51.52, lon=-0.14),
        LatLon(lat=51.52, lon=-0.12),
        LatLon(lat=51.50, lon=-0.12),
        LatLon(lat=51.50, lon=-0.14),
    ]

    # Stub the cache: always return both properties as a cache hit
    cache = MagicMock(spec=ModelCache)
    cache.get.return_value = [prop_pass, prop_fail]

    results = []
    async for batch in get_property_ids_in_area_cached(
        bounding_poly,
        tile_coords,
        "RENT",
        cache,
        predicate=lambda p: (p.number_of_images or 0) > 2,
    ):
        results.extend(batch)

    assert prop_pass in results
    assert prop_fail not in results
