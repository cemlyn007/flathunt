import rightmove.app
from unittest import mock
import json
import tempfile
import os


class TestApp:
    SEARCH_LOCATION = "STATION^245"

    @mock.patch("webbrowser.open_new_tab")
    @mock.patch("builtins.input")
    def test_app_search_no_smoke(
        self, mock_input: mock.Mock, mock_open_new_tab: mock.Mock
    ) -> None:
        with open("tests/example.json") as f:
            mocked_response = json.load(f)
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file_path = os.path.join(tmpdir, "history.json")
            commute_coordinates = [(0, 0)]
            app = rightmove.app.App(cache_file_path, commute_coordinates, False)

            with mock.patch("rightmove.api.Rightmove._search") as mock_search:
                mock_search.return_value = mocked_response
                app.search(self.SEARCH_LOCATION, 2000, 0.5, 7)
                mock_open_new_tab.call_count == len(mocked_response["properties"]) * (
                    1 + len(commute_coordinates)
                )

    @mock.patch("webbrowser.open_new_tab")
    @mock.patch("builtins.input")
    def test_app_search_cache(
        self, mock_input: mock.Mock, mock_open_new_tab: mock.Mock
    ) -> None:
        with open("tests/example.json") as f:
            mocked_response = json.load(f)
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file_path = os.path.join(tmpdir, "history.json")
            with open(cache_file_path, "w") as f:
                json.dump(mocked_response["properties"][1:], f)
            commute_coordinates = [(0, 0)]
            app = rightmove.app.App(cache_file_path, commute_coordinates, False)
            with mock.patch("rightmove.api.Rightmove._search") as mock_search:
                mock_search.return_value = mocked_response
                app.search(self.SEARCH_LOCATION, 2000, 0.5, 7)
                mock_open_new_tab.call_count == 1 + len(commute_coordinates)
