import os

import pytest

from tfl.api._transport import get_ratelimited_client
from tfl.api.stop_points import get_stop_points_by_mode
from tfl.models import ModeId, StopPointDetail

# ---------------------------------------------------------------------------
# Regression tests - real network calls
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.skipif(
    not os.environ.get("FLATHUNT__TFL_API_KEY"),
    reason="requires FLATHUNT__TFL_API_KEY in environment or .env file",
)
async def test_get_stop_points_by_mode_returns_stop_points():
    """Stop points for all modes are returned as StopPointDetail objects."""
    async with get_ratelimited_client() as client:
        result = await get_stop_points_by_mode(client, list(ModeId))
    assert isinstance(result, list)
    assert len(result) > 0
    assert all(isinstance(sp, StopPointDetail) for sp in result)
