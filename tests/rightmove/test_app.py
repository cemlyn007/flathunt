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
        min_bedrooms=1,
        max_price=2000,
        number_of_properties_per_page=24,
        radius=0.5,
        sort_type=api.SortType.MOST_RECENT,
        include_let_agreed=False,
        is_fetching=True,
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
            cache_filepath = os.path.join(tmpdir, "history.json")
            # GIVEN: A cache file that is empty.
            cache = rightmove.property_cache.PropertyCache(cache_filepath)
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
            cache_filepath = os.path.join(tmpdir, "history.json")
            # GIVEN: All properties in the search response are cached
            #  except one of the properties.
            with open(cache_filepath, "w") as file:
                json.dump(
                    [
                        property
                        for property in search_response["properties"]
                        if property["id"] != least_common_property_id
                    ],
                    file,
                )
            commute_coordinates = [(0.0, 0.0)]
            cache = rightmove.property_cache.PropertyCache(cache_filepath)
            app = rightmove.app.App(commute_coordinates, cache)
            with mock.patch("rightmove.api._RawRightmove._search") as mock_search:
                mock_search.return_value = search_response
                app.search(query)
                # THEN: The app should only show the one property that is not in the cache.
                assert mock_open_new_tab.call_count == 1 + len(commute_coordinates)
