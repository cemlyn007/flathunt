import os

import pytest

from tfl.api._transport import get_ratelimited_client
from tfl.api.timetable import Direction, get_timetable, get_timetable_between_stops
from tfl.models import TimetableResponse

# ---------------------------------------------------------------------------
# Regression tests – real network calls
# ---------------------------------------------------------------------------

# Central line: Bond Street -> Marble Arch (adjacent stops, outbound)
_LINE_ID = "central"
_FROM_STOP = "940GZZLUBND"  # Bond Street
_TO_STOP = "940GZZLUMBA"  # Marble Arch


@pytest.fixture
def app_key() -> str:
    return os.environ.get("FLATHUNT__TFL_API_KEY", "")


@pytest.mark.skipif(
    not os.environ.get("FLATHUNT__TFL_API_KEY"),
    reason="requires FLATHUNT__TFL_API_KEY in environment or .env file",
)
async def test_get_timetable_returns_timetable_response(app_key: str):
    """Timetable for Central line from Bond Street returns a TimetableResponse."""
    async with get_ratelimited_client() as client:
        result = await get_timetable(
            client,
            station_id=_LINE_ID,
            from_stop_point_id=_FROM_STOP,
            app_key=app_key,
            direction=Direction.OUTBOUND,
        )
    assert isinstance(result, TimetableResponse)


@pytest.mark.skipif(
    not os.environ.get("FLATHUNT__TFL_API_KEY"),
    reason="requires FLATHUNT__TFL_API_KEY in environment or .env file",
)
async def test_get_timetable_between_stops_returns_timetable_response(app_key: str):
    """Timetable for Central line between Bond Street and Marble Arch returns a TimetableResponse."""
    async with get_ratelimited_client() as client:
        result = await get_timetable_between_stops(
            client,
            line_id=_LINE_ID,
            from_stop_point_id=_FROM_STOP,
            to_stop_point_id=_TO_STOP,
            app_key=app_key,
        )
    assert isinstance(result, TimetableResponse)
