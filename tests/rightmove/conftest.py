import os
import json
import pytest
from typing import Any


@pytest.fixture
def search_response() -> dict[str, Any]:
    example_file_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "fixtures", "example_search.json"
    )
    with open(example_file_path) as file:
        mocked_response = json.load(file)
    return mocked_response
