import pytest

from rightmove.api import (
    DontShow,
    FurnishType,
    MustHave,
    PropertyType,
    Rightmove,
    SearchQuery,
    SortType,
    polyline_identifier,
)
from rightmove.models import ListingProperty, MapProperty


@pytest.fixture
def fully_populated_search_query() -> SearchQuery:
    """Fixture to provide a SearchQuery with all parameters populated."""
    return SearchQuery(
        location_identifier="REGION^87490",
        min_bedrooms=2,
        max_bedrooms=4,
        min_price=1000,
        max_price=2000,
        min_bathrooms=1,
        max_bathrooms=3,
        number_of_properties_per_page=24,
        radius=5.0,
        sort_type=SortType.MOST_RECENT,
        must_have=[MustHave.GARDEN, MustHave.PARKING],
        dont_show=[DontShow.HOUSE_SHARE, DontShow.RETIREMENT, DontShow.STUDENT],
        furnish_types=[
            FurnishType.FURNISHED,
            FurnishType.PART_FURNISHED,
            FurnishType.UNFURNISHED,
        ],
        property_types=[
            PropertyType.FLAT,
            PropertyType.DETACHED,
            PropertyType.SEMI_DETACHED,
            PropertyType.TERRACED,
        ],
        is_fetching=True,
        max_days_since_added=7,
        include_let_agreed=False,
    )


@pytest.mark.regression
async def test_listing_search_all_params(
    fully_populated_search_query: SearchQuery,
) -> None:
    """Smoke test that the listing search endpoint accepts all supported parameters."""
    rightmove = Rightmove()
    assert len(await rightmove.search(fully_populated_search_query))


@pytest.mark.regression
async def test_listing_search_e2e() -> None:
    """End-to-end test that the listing search endpoint returns valid properties."""
    query = SearchQuery(
        location_identifier="OUTCODE^1864",  # NW8
        number_of_properties_per_page=24,
        sort_type=SortType.MOST_RECENT,
        property_types=[
            PropertyType.FLAT,
            PropertyType.DETACHED,
            PropertyType.SEMI_DETACHED,
            PropertyType.TERRACED,
        ],
        dont_show=[DontShow.HOUSE_SHARE, DontShow.RETIREMENT, DontShow.STUDENT],
        min_bedrooms=1,
        max_bedrooms=10,
        is_fetching=True,
        channel="BUY",
    )
    rightmove = Rightmove()
    properties = await rightmove.search(query)

    assert len(properties) > 0, "Expected at least one property in NW8"
    for prop in properties:
        assert isinstance(prop, ListingProperty)
        assert isinstance(prop.id, int)
        assert isinstance(prop.location.latitude, float)
        assert isinstance(prop.location.longitude, float)
        assert isinstance(prop.price.amount, int)
        assert isinstance(prop.display_address, str)
        assert prop.channel == "BUY", (
            f"property {prop.id} has unexpected channel {prop.channel!r}"
        )
        assert prop.country_code == "GB", (
            f"property {prop.id} has unexpected country_code {prop.country_code!r}"
        )
        assert isinstance(prop.commercial, bool)
        assert isinstance(prop.residential, bool)
        assert isinstance(prop.keywords, list)


# Small polygon covering part of central London (Soho / Covent Garden area).
_LONDON_POLYGON: list[tuple[float, float]] = [
    (51.510, -0.135),
    (51.516, -0.135),
    (51.516, -0.118),
    (51.510, -0.118),
    (51.510, -0.135),
]


@pytest.mark.regression
async def test_map_search_e2e() -> None:
    """End-to-end test that the map search endpoint returns valid property locations."""
    query = SearchQuery(
        location_identifier=polyline_identifier(_LONDON_POLYGON),
        number_of_properties_per_page=95,
        sort_type=SortType.MOST_RECENT,
        property_types=[
            PropertyType.FLAT,
            PropertyType.DETACHED,
            PropertyType.SEMI_DETACHED,
            PropertyType.TERRACED,
        ],
        dont_show=[DontShow.HOUSE_SHARE, DontShow.RETIREMENT, DontShow.STUDENT],
        min_bedrooms=1,
        max_bedrooms=10,
        is_fetching=True,
        channel="BUY",
    )
    rightmove = Rightmove()
    locations, count = await rightmove.map_search(query)

    assert isinstance(count, int)
    assert count >= 0
    assert len(locations) > 0, "Expected at least one property in central London"
    assert len(locations) <= count
    for prop in locations:
        assert isinstance(prop, MapProperty)
        assert isinstance(prop.id, int)
        assert isinstance(prop.location.latitude, float)
        assert isinstance(prop.location.longitude, float)
        assert isinstance(prop.property_url, str)
        assert isinstance(prop.price.amount, int)
        assert isinstance(prop.display_address, str)
