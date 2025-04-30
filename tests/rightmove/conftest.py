import os
import json
import pytest
from typing import Any


@pytest.fixture
def search_response() -> dict[str, Any]:
    example_filepath = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "fixtures", "example_search.json"
    )
    with open(example_filepath) as file:
        mocked_response = json.load(file)
    return mocked_response
