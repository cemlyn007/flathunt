import collections
from typing import Any
import rightmove.app
import rightmove.property_cache
from rightmove import api
from unittest import mock
import json
import tempfile
import os
import pytest


@pytest.fixture
def query() -> api.SearchQuery:
    return api.SearchQuery(
        location_identifier="STATION^245",
        min_bedrooms=1,  # Reasonable minimum bedrooms
        max_price=2000,
        number_of_properties_per_page=24,
        radius=0.5,
        sort_type=api.SortType.MOST_RECENT,  # Use the defined enum value
        include_let_agreed=False,
        view_type="LIST",
        dont_show=["houseShare", "retirement", "student", "commercial"],
        furnish_types=["furnished", "partFurnished", "unfurnished"],
        channel="RENT",  # Assuming rental properties
        area_size_unit="sqft",
        currency_code="GBP",
        is_fetching=True,
        max_days_since_added=None,  # Optional field
    )


class TestApp:
    @mock.patch("webbrowser.open_new_tab")
    @mock.patch("builtins.input")
    def test_app_search_no_smoke(
        self,
        mock_input: mock.Mock,
        mock_open_new_tab: mock.Mock,
        query: api.SearchQuery,
        search_response: dict[str, Any],
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file_path = os.path.join(tmpdir, "history.json")
            # GIVEN: A cache file that is empty.
            cache = rightmove.property_cache.PropertyCache(cache_file_path)
            commute_coordinates = [(0.0, 0.0)]
            app = rightmove.app.App(commute_coordinates, cache)

            with mock.patch("rightmove.api._RawRightmove._search") as mock_search:
                mock_search.return_value = search_response
                app.search(query)
                # THEN: The app should show all properties in the search response.
                assert mock_open_new_tab.call_count == len(
                    search_response["properties"]
                ) * (1 + len(commute_coordinates))

    @mock.patch("webbrowser.open_new_tab")
    @mock.patch("builtins.input")
    def test_app_search_cache(
        self,
        mock_input: mock.Mock,
        mock_open_new_tab: mock.Mock,
        query: api.SearchQuery,
        search_response: dict[str, Any],
    ) -> None:
        least_common_property_id, count = min(
            collections.Counter(
                [property["id"] for property in search_response["properties"]]
            ).items(),
            key=lambda pair: pair[1],
        )
        if count > 1:
            pytest.fail(
                f"Test data is not unique. Property ID {least_common_property_id} appears {count} times."
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file_path = os.path.join(tmpdir, "history.json")
            # GIVEN: All properties in the search response are cached
            #  except one of the properties.
            with open(cache_file_path, "w") as file:
                json.dump(
                    [
                        property
                        for property in search_response["properties"]
                        if property["id"] != least_common_property_id
                    ],
                    file,
                )
            commute_coordinates = [(0.0, 0.0)]
            cache = rightmove.property_cache.PropertyCache(cache_file_path)
            app = rightmove.app.App(commute_coordinates, cache)
            with mock.patch("rightmove.api._RawRightmove._search") as mock_search:
                mock_search.return_value = search_response
                app.search(query)
                # THEN: The app should only show the one property that is not in the cache.
                assert mock_open_new_tab.call_count == 1 + len(commute_coordinates)


# class SearchQuery(pydantic.BaseModel):
#     location_identifier: str
#     min_bedrooms: int
#     max_price: int
#     number_of_properties_per_page: int
#     radius: float
#     "In Miles."
#     sort_type: SortType
#     include_let_agreed: bool
#     view_type: Literal["LIST"]
#     dont_show: list[Literal["houseShare", "retirement", "student", "commercial"]]
#     furnish_types: list[Literal["furnished", "partFurnished", "unfurnished"]]
#     channel: Literal["RENT", "BUY"]
#     area_size_unit: Literal["sqft", "sqm"]
#     currency_code: Literal["GBP"]
#     is_fetching: bool
#     max_days_since_added: Optional[int]
