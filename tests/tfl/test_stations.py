import os

import pytest

from tfl.api.endpoints.stations import get_stations_facilities
from tfl.models import Root

# ---------------------------------------------------------------------------
# Regression tests - real network calls
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("FLATHUNT__TFL_API_KEY"),
    reason="requires FLATHUNT__TFL_API_KEY in environment or .env file",
)
async def test_get_stations_facilities_returns_root():
    """Station facilities XML feed is fetched and parsed into a Root model."""
    result = await get_stations_facilities()
    assert isinstance(result, Root)
    assert len(result.stations.station) > 0
