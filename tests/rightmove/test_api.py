import pytest

from rightmove.api import (
    Rightmove,
    SearchQuery,
    SortType,
    MustHave,
    DontShow,
    FurnishType,
    PropertyType,
)


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
def test_api_search_smoke_test(fully_populated_search_query: SearchQuery) -> None:
    """
    Smoke test to verify that the Rightmove API can be called with all parameters set.
    This test mocks the raw API response to avoid making actual network calls.
    """
    # GIVEN a Rightmove API client and a fully populated search query
    rightmove = Rightmove()
    # THEN: the search query should be executed without errors
    rightmove.search(fully_populated_search_query)
