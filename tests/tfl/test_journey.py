import datetime
import os
from unittest.mock import AsyncMock

import httpx
import pytest

import tfl.api
from tfl.api._http import get_ratelimited_client
from tfl.api.endpoints.journey import (
    build_journey_parameters,
    build_journey_url,
    get_journey_results,
)
from tfl.exceptions import TflApiError
from tfl.models import JourneyResults, ModeId

# ---------------------------------------------------------------------------
# Unit tests - pure functions, no network
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
    arrival = datetime.datetime(2026, 4, 7, 9, 0, 0, tzinfo=datetime.UTC)
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


# Exact TfL error body observed for 940GZZLUMHL → 940GZZLUWRR on 2026-04-19.
_TFL_500_BODY = (
    b'{"$type":"Tfl.Api.Presentation.Entities.ApiError, Tfl.Api.Presentation.Entities",'
    b'"timestampUtc":"2026-04-19T11:25:55.6412433Z","name":"Internal",'
    b'"exceptionType":"HttpRequestException","httpStatusCode":500,'
    b'"httpStatus":"InternalServerError",'
    b'"relativeUri":"/Journey/JourneyResults/940GZZLUMHL/to/940GZZLUWRR",'
    b'"message":"An internal server error occurred."}'
)

_PROBLEMATIC_MODES = [
    ModeId.TUBE,
    ModeId.OVERGROUND,
    ModeId.DLR,
    ModeId.ELIZABETH_LINE,
    ModeId.WALKING,
]


async def test_get_journey_results_raises_tfl_api_error_for_http_500():
    """HTTP 500 from TfL raises TflApiError and is not retried.

    Reproduces the error propagation for the stop pair 940GZZLUMHL → 940GZZLUWRR:

    1. TfL returns HTTP 500 with exceptionType=HttpRequestException.
    2. ``get()`` in ``_transport.py`` catches ``httpx.HTTPStatusError`` and
       re-raises it as ``TflApiError`` (because exceptionType is not
       "EntityNotFoundException").
    3. The ``@retry`` decorator calls ``_is_retryable_error(TflApiError)``
       which returns ``False`` — so no retry occurs; the client is called
       exactly once.
    4. ``TflApiError`` propagates out of ``get_journey_results``; the
       ``transport`` asset's ``process_query_queue`` only catches
       ``JourneyNotFoundError``, so the uncaught ``TflApiError`` crashes the
       entire asset.
    """
    request = httpx.Request(
        "GET",
        "https://api.tfl.gov.uk/Journey/JourneyResults/940GZZLUMHL/to/940GZZLUWRR",
    )
    mock_response = httpx.Response(
        status_code=500,
        content=_TFL_500_BODY,
        headers={"content-type": "application/json; charset=utf-8"},
        request=request,
    )
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_response

    with pytest.raises(TflApiError) as exc_info:
        await get_journey_results(
            client=mock_client,
            from_location="940GZZLUMHL",
            to_location="940GZZLUWRR",
            arrival_datetime=datetime.datetime(2026, 4, 20, 9, 0, tzinfo=datetime.UTC),
            modes=_PROBLEMATIC_MODES,
            use_multi_modal_call=False,
            app_key="testkey",
        )

    assert exc_info.value.http_status_code == 500
    assert exc_info.value.exception_type == "HttpRequestException"
    # TflApiError is non-retryable: the underlying HTTP client was called once.
    assert mock_client.get.call_count == 1


# ---------------------------------------------------------------------------
# Regression tests - real network calls
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
    arrival = datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(hours=2)
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


@pytest.mark.regression
@pytest.mark.skipif(
    not os.environ.get("FLATHUNT__TFL_API_KEY"),
    reason="requires FLATHUNT__TFL_API_KEY in environment or .env file",
)
async def test_get_journey_results_500_for_problematic_stop_pair(app_key: str):
    """Reproduce HTTP 500 from TfL for the stop pair 940GZZLUMHL → 940GZZLUWRR.

    Diagnosis
    ---------
    The ``transport`` Dagster asset calls ``get_journey_results`` for every
    *combination* of stops returned by ``get_stop_points_by_line``, using
    their NaPTAN IDs as journey-planner endpoints.  TfL lists these stops as
    belonging to a line, but its journey planner fails with HTTP 500 /
    ``exceptionType=HttpRequestException`` when they are used as
    origin/destination.

    The error propagation is:

    1. TfL returns HTTP 500 → ``response.raise_for_status()`` raises
       ``httpx.HTTPStatusError`` inside ``get()``.
    2. ``get()`` parses the JSON body; because ``exceptionType`` is
       ``"HttpRequestException"`` (not ``"EntityNotFoundException"``) it
       raises ``TflApiError`` instead.
    3. The ``@retry`` decorator calls ``_is_retryable_error(TflApiError)``
       → returns ``False`` → no retry, exception re-raised immediately.
    4. ``process_query_queue`` in ``transport.py`` only catches
       ``JourneyNotFoundError``; ``TflApiError`` propagates uncaught and
       crashes the entire ``transport`` asset.
    """
    arrival = tfl.api.get_next_datetime(datetime.time(9, 0, 0, tzinfo=datetime.UTC))
    async with get_ratelimited_client() as client:
        with pytest.raises(TflApiError) as exc_info:
            await get_journey_results(
                client=client,
                from_location="940GZZLUMHL",
                to_location="940GZZLUWRR",
                arrival_datetime=arrival,
                modes=_PROBLEMATIC_MODES,
                use_multi_modal_call=False,
                app_key=app_key,
            )
    assert exc_info.value.http_status_code == 500
    assert exc_info.value.exception_type == "HttpRequestException"
