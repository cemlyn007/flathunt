import os

import pytest

from tfl.api._http import get_ratelimited_client
from tfl.api.endpoints.lines import (
    get_all_lines_routes,
    get_lines_by_mode,
    get_stop_points_by_line,
)
from tfl.models import Line, ModeId, StopPointDetail

# ---------------------------------------------------------------------------
# Regression tests - real network calls
# ---------------------------------------------------------------------------

_TUBE_LINE_ID = "central"


@pytest.fixture
def app_key() -> str:
    return os.environ.get("FLATHUNT__TFL_API_KEY", "")


@pytest.mark.skipif(
    not os.environ.get("FLATHUNT__TFL_API_KEY"),
    reason="requires FLATHUNT__TFL_API_KEY in environment or .env file",
)
async def test_get_all_lines_routes_returns_lines(app_key: str):
    """Smoke test that /Line/Route returns a non-empty list of Line objects."""
    async with get_ratelimited_client() as client:
        result = await get_all_lines_routes(client, app_key)
    assert isinstance(result, list)
    assert len(result) > 0
    assert all(isinstance(line, Line) for line in result)


@pytest.mark.skipif(
    not os.environ.get("FLATHUNT__TFL_API_KEY"),
    reason="requires FLATHUNT__TFL_API_KEY in environment or .env file",
)
async def test_get_lines_by_mode_returns_tube_lines(app_key: str):
    """Requesting tube lines by mode returns only tube-mode lines."""
    async with get_ratelimited_client() as client:
        result = await get_lines_by_mode(client, [ModeId.TUBE], app_key)
    assert isinstance(result, list)
    assert len(result) > 0
    assert all(isinstance(line, Line) for line in result)
    assert all(line.mode_name == ModeId.TUBE for line in result)


@pytest.mark.skipif(
    not os.environ.get("FLATHUNT__TFL_API_KEY"),
    reason="requires FLATHUNT__TFL_API_KEY in environment or .env file",
)
async def test_get_stop_points_by_line_returns_stop_points(app_key: str):
    """Stop points for the Central line are returned as StopPointDetail objects."""
    async with get_ratelimited_client() as client:
        result = await get_stop_points_by_line(client, _TUBE_LINE_ID, app_key)
    assert isinstance(result, list)
    assert len(result) > 0
    assert all(isinstance(sp, StopPointDetail) for sp in result)
