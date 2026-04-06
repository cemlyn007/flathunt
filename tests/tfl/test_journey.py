import datetime
import os

import pytest

from tfl.api._transport import get_ratelimited_client
from tfl.api.journey import (
    build_journey_parameters,
    build_journey_url,
    get_journey_results,
)
from tfl.models import JourneyResults, ModeId

# ---------------------------------------------------------------------------
# Unit tests – pure functions, no network
# ---------------------------------------------------------------------------


def test_build_journey_url_with_coordinates():
    url = build_journey_url((51.5074, -0.1278), (51.5033, -0.1195))
    assert url == "/Journey/JourneyResults/51.5074%2C-0.1278/to/51.5033%2C-0.1195"


def test_build_journey_url_with_strings():
    url = build_journey_url("1000012", "1000016")
    assert url == "/Journey/JourneyResults/1000012/to/1000016"


def test_build_journey_url_string_with_spaces_is_encoded():
    url = build_journey_url("Bank Station", "London Bridge")
    assert " " not in url


def test_build_journey_parameters_departing_now():
    params = build_journey_parameters(
        arrival_datetime=None,
        modes=[ModeId.TUBE],
        use_multi_modal_call=False,
        app_key="testkey",
    )
    assert params["app_key"] == "testkey"
    assert params["mode"] == "tube"
    assert params["multiModalCall"] is False
    assert params["timeIs"] == "departing"
    assert "date" in params
    assert "time" in params


def test_build_journey_parameters_arriving_at():
    arrival = datetime.datetime(2026, 4, 7, 9, 0, 0, tzinfo=datetime.timezone.utc)
    params = build_journey_parameters(
        arrival_datetime=arrival,
        modes=[ModeId.TUBE, ModeId.WALKING],
        use_multi_modal_call=True,
        app_key="testkey",
    )
    assert params["timeIs"] == "arriving"
    assert params["date"] == "20260407"
    assert params["time"] == "0900"
    assert params["mode"] == "tube,walking"
    assert params["multiModalCall"] is True


def test_build_journey_parameters_arrival_datetime_converted_to_utc():
    # Provide a datetime in UTC+1 (BST), equivalent to 08:00 UTC
    bst = datetime.timezone(datetime.timedelta(hours=1))
    arrival = datetime.datetime(2026, 4, 7, 9, 0, 0, tzinfo=bst)
    params = build_journey_parameters(
        arrival_datetime=arrival,
        modes=[ModeId.TUBE],
        use_multi_modal_call=False,
        app_key="",
    )
    assert params["date"] == "20260407"
    assert params["time"] == "0800"


def test_build_journey_parameters_multiple_modes():
    params = build_journey_parameters(
        arrival_datetime=None,
        modes=[ModeId.TUBE, ModeId.DLR, ModeId.ELIZABETH_LINE],
        use_multi_modal_call=False,
        app_key="",
    )
    assert params["mode"] == "tube,dlr,elizabeth-line"


# ---------------------------------------------------------------------------
# Regression tests – real network calls
# ---------------------------------------------------------------------------

# Well-known coordinates: Westminster -> Waterloo
_FROM = (51.5007, -0.1246)
_TO = (51.5036, -0.1143)


@pytest.fixture
def app_key() -> str:
    return os.environ.get("FLATHUNT__TFL_API_KEY", "")


@pytest.mark.skipif(
    not os.environ.get("FLATHUNT__TFL_API_KEY"),
    reason="requires FLATHUNT__TFL_API_KEY in environment or .env file",
)
async def test_get_journey_results_returns_journey_results(app_key: str):
    """Smoke test that a coordinate-based journey query returns JourneyResults."""
    async with get_ratelimited_client() as client:
        result = await get_journey_results(
            client=client,
            from_location=_FROM,
            to_location=_TO,
            arrival_datetime=None,
            modes=[ModeId.TUBE, ModeId.WALKING],
            use_multi_modal_call=False,
            app_key=app_key,
        )
    assert isinstance(result, JourneyResults)
    assert len(result.journeys) > 0


@pytest.mark.skipif(
    not os.environ.get("FLATHUNT__TFL_API_KEY"),
    reason="requires FLATHUNT__TFL_API_KEY in environment or .env file",
)
async def test_get_journey_results_with_arrival_datetime(app_key: str):
    """Journey query with a specific arrival datetime returns JourneyResults."""
    arrival = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(
        hours=2
    )
    async with get_ratelimited_client() as client:
        result = await get_journey_results(
            client=client,
            from_location=_FROM,
            to_location=_TO,
            arrival_datetime=arrival,
            modes=[ModeId.TUBE, ModeId.WALKING],
            use_multi_modal_call=False,
            app_key=app_key,
        )
    assert isinstance(result, JourneyResults)
    assert len(result.journeys) > 0


@pytest.mark.skipif(
    not os.environ.get("FLATHUNT__TFL_API_KEY"),
    reason="requires FLATHUNT__TFL_API_KEY in environment or .env file",
)
async def test_get_journey_results_multi_modal(app_key: str):
    """Multi-modal call flag is accepted and returns JourneyResults."""
    async with get_ratelimited_client() as client:
        result = await get_journey_results(
            client=client,
            from_location=_FROM,
            to_location=_TO,
            arrival_datetime=None,
            modes=[ModeId.TUBE, ModeId.WALKING, ModeId.NATIONAL_RAIL],
            use_multi_modal_call=True,
            app_key=app_key,
        )
    assert isinstance(result, JourneyResults)
    assert len(result.journeys) > 0
