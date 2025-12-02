import datetime
import enum
import logging
import urllib.parse
from collections.abc import Iterable
from typing import Any, Optional

import httpx
from httpx_limiter.async_rate_limited_transport import AsyncRateLimitedTransport
from httpx_limiter.rate import Rate
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from tfl import exceptions, models

logger = logging.getLogger(__name__)

API_BASE_URL = "https://api.tfl.gov.uk"
STATION_FACILITIES_URL = (
    "https://tfl.gov.uk/tfl/syndication/feeds/stations-facilities.xml"
)

# get	/Place/Meta/Categories
# https://api.tfl.gov.uk/Place/Meta/Categories


class Direction(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class Tfl:
    def __init__(
        self,
        app_key: str,
    ) -> None:
        self._app_key = app_key
        self._throttled_client = get_ratelimited_client()

    async def get_stations_facilities(self) -> models.Root:
        return await get_stations_facilities()

    async def get_stop_points_by_mode(
        self, modes: Iterable[models.ModeId]
    ) -> list[models.StopPointDetail]:
        return await get_stop_points_by_mode(self._throttled_client, modes)

    async def get_all_lines_routes(self) -> list[models.Line]:
        return await get_all_lines_routes(self._throttled_client, self._app_key)

    async def get_lines_by_mode(
        self, modes: Iterable[models.ModeId]
    ) -> list[models.Line]:
        return await get_lines_by_mode(self._throttled_client, modes, self._app_key)

    async def get_stop_points_by_line(
        self, line_id: str
    ) -> list[models.StopPointDetail]:
        return await get_stop_points_by_line(
            self._throttled_client, line_id, self._app_key
        )

    async def get_journey_results(
        self,
        from_location: tuple[float, float] | str,
        to_location: tuple[float, float] | str,
        arrival_datetime: Optional[datetime.datetime],
        modes: Iterable[models.ModeId],
        use_multi_modal_call: bool,
    ) -> models.JourneyResults | models.DisambiguationResult:
        return await get_journey_results(
            self._throttled_client,
            from_location,
            to_location,
            arrival_datetime,
            modes,
            use_multi_modal_call,
            app_key=self._app_key,
        )

    async def get_timetable(
        self,
        station_id: str,
        from_stop_point_id: str,
        direction: Direction | None = None,
    ) -> models.TimetableResponse:
        return await get_timetable(
            self._throttled_client,
            station_id,
            from_stop_point_id,
            self._app_key,
            direction,
        )

    async def get_timetable_between_stops(
        self,
        line_id: str,
        from_stop_point_id: str,
        to_stop_point_id: str,
    ) -> models.TimetableResponse:
        return await get_timetable_between_stops(
            self._throttled_client,
            line_id,
            from_stop_point_id,
            to_stop_point_id,
            self._app_key,
        )


async def get_stations_facilities() -> models.Root:
    async with httpx.AsyncClient() as client:
        response = await client.get(STATION_FACILITIES_URL)
        response.raise_for_status()
        content = response.content
    text = content.decode()
    clean_text = " ".join(text.split())
    return models.Root.from_xml(clean_text)


async def get_stop_points_by_mode(
    client: httpx.AsyncClient, modes: Iterable[models.ModeId]
) -> list[models.StopPointDetail]:
    """Get all stop points for the given transport modes.

    Args:
        client: The HTTP client to use for the request.
        modes: The transport modes (e.g., [ModeId.TUBE, ModeId.BUS]).

    Returns:
        A list of StopPointDetail objects for the given modes.
    """
    modes_str = ",".join(mode.value for mode in modes)
    url = f"/StopPoint/Mode/{modes_str}"
    status_code, content = await get(client, url, {})
    response = models.StopPointsResponse.model_validate_json(content)
    return response.stop_points


async def get_all_lines_routes(
    client: httpx.AsyncClient, app_key: str
) -> list[models.Line]:
    """Get all lines with their route information.

    Args:
        client: The HTTP client to use for the request.
        app_key: The application key for authentication.

    Returns:
        A list of Line objects containing route information.
    """
    url = "/Line/Route"
    status_code, content = await get(client, url, {"app_key": app_key})
    return models.LinesRoutesResponse.validate_json(content)


async def get_lines_by_mode(
    client: httpx.AsyncClient, modes: Iterable[models.ModeId], app_key: str
) -> list[models.Line]:
    """Get all lines for a given transport mode.

    Args:
        client: The HTTP client to use for the request.
        modes: The transport modes (e.g., [ModeId.TUBE, ModeId.BUS]).
        app_key: The application key for authentication.

    Returns:
        A list of Line objects for the given modes.
    """
    modes_str = ",".join(mode.value for mode in modes)
    url = f"/Line/Mode/{modes_str}"
    status_code, content = await get(client, url, {"app_key": app_key})
    return models.LineList.validate_json(content)


async def get_stop_points_by_line(
    client: httpx.AsyncClient, line_id: str, app_key: str
) -> list[models.StopPointDetail]:
    """Get all stop points for a specific line.

    Args:
        client: The HTTP client to use for the request.
        line_id: The line ID (e.g., "victoria", "northern", "elizabeth").
        app_key: The application key for authentication.

    Returns:
        A list of StopPointDetail objects for the given line.
    """
    url = f"/Line/{line_id}/StopPoints"
    status_code, content = await get(client, url, {"app_key": app_key})
    return models.StopPointList.validate_json(content)


async def get_journey_results(
    client: httpx.AsyncClient,
    from_location: tuple[float, float] | str,
    to_location: tuple[float, float] | str,
    arrival_datetime: Optional[datetime.datetime],
    modes: Iterable[models.ModeId],
    use_multi_modal_call: bool,
    app_key: str,
) -> models.JourneyResults | models.DisambiguationResult:
    url = build_journey_url(from_location, to_location)
    parameters = build_journey_parameters(
        arrival_datetime, modes, use_multi_modal_call, app_key
    )
    status_code, content = await get(client, url, parameters)
    if status_code == 300:
        return models.DisambiguationResult.model_validate_json(content, strict=True)
    return models.JourneyResults.model_validate_json(content, strict=True)


async def get_timetable(
    client: httpx.AsyncClient,
    station_id: str,
    from_stop_point_id: str,
    app_key: str,
    direction: Direction | None = None,
) -> models.TimetableResponse:
    url = f"/Line/{station_id}/Timetable/{from_stop_point_id}"
    parameters = {"direction": direction.value} if direction else {}
    parameters["app_key"] = app_key
    _, content = await get(client, url, parameters)
    return models.TimetableResponse.model_validate_json(content, strict=True)


async def get_timetable_between_stops(
    client: httpx.AsyncClient,
    line_id: str,
    from_stop_point_id: str,
    to_stop_point_id: str,
    app_key: str,
) -> models.TimetableResponse:
    url = f"/Line/{line_id}/Timetable/{from_stop_point_id}/to/{to_stop_point_id}"
    status_code, content = await get(client, url, {"app_key": app_key})
    return models.TimetableResponse.model_validate_json(content, strict=True)


def get_ratelimited_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=API_BASE_URL,
        transport=AsyncRateLimitedTransport.create(
            Rate.create(magnitude=(25 - 1), duration=3)
        ),
    )


def _is_retryable_error(exception: BaseException) -> bool:
    """Check if exception is an HTTP 5xx server error or 429 rate limit error."""
    if isinstance(
        exception, (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError)
    ):
        return True
    elif not isinstance(exception, httpx.HTTPStatusError):
        return False
    status_code = exception.response.status_code
    return status_code >= 500 or status_code == 429


def _get_wait_time(retry_state) -> float:
    """Get wait time based on retry-after header or exponential backoff."""
    if retry_state.outcome.exception():
        exception = retry_state.outcome.exception()
        if isinstance(exception, httpx.HTTPStatusError):
            retry_after = exception.response.headers.get("retry-after")
            if retry_after:
                try:
                    return float(retry_after)
                except ValueError:
                    pass
    # Fall back to exponential backoff
    return wait_exponential(multiplier=1, min=1, max=10)(retry_state)


@retry(
    retry=retry_if_exception(_is_retryable_error),
    stop=stop_after_attempt(10),
    wait=_get_wait_time,
    reraise=True,
)
async def get(
    client: httpx.AsyncClient, url: str, parameters: dict[str, Any]
) -> tuple[int, bytes]:
    try:
        response = await client.get(url, params=parameters)
        # Disambigious Results
        if response.status_code == 300:
            return response.status_code, response.content
        response.raise_for_status()
        return response.status_code, response.content
    except httpx.HTTPStatusError as e:
        e.add_note(e.response.text)
        logger.error(
            "HTTP error %s for URL %s with headers %s and content %s",
            e.response.status_code,
            url,
            e.response.headers,
            e.response.content,
        )
        if e.response.status_code == 404:
            try:
                error_data = e.response.json()
                message = error_data.get("message", "Not found")
                exception_type = error_data.get("exceptionType")

                if exception_type == "EntityNotFoundException":
                    raise exceptions.JourneyNotFoundError(
                        message=message,
                        http_status_code=error_data.get("httpStatusCode"),
                        exception_type=exception_type,
                        timestamp_utc=error_data.get("timestampUtc"),
                        relative_uri=error_data.get("relativeUri"),
                    ) from e
                else:
                    raise exceptions.TflApiError(
                        message=message,
                        http_status_code=(
                            error_data.get("httpStatusCode") or e.response.status_code
                        ),
                        exception_type=exception_type,
                        timestamp_utc=error_data.get("timestampUtc"),
                        relative_uri=error_data.get("relativeUri"),
                    ) from e
            except (ValueError, KeyError):
                # If JSON parsing fails, re-raise the original exception
                raise
        raise


def build_journey_url(
    from_location: tuple[float, float] | str, to_location: tuple[float, float] | str
) -> str:
    from_location_encoded = urllib.parse.quote(
        from_location
        if isinstance(from_location, str)
        else ",".join(map(str, from_location))
    )
    to_location_encoded = urllib.parse.quote(
        to_location if isinstance(to_location, str) else ",".join(map(str, to_location))
    )
    url = f"/Journey/JourneyResults/{from_location_encoded}/to/{to_location_encoded}"
    return url


def build_journey_parameters(
    arrival_datetime: datetime.datetime | None,
    modes: Iterable[models.ModeId],
    use_multi_modal_call: bool,
    app_key: str,
):
    parameters = {
        "app_key": app_key,
        "mode": ",".join(mode.value for mode in modes),
        "multiModalCall": use_multi_modal_call,
    }
    if arrival_datetime is None:
        departure_datetime = datetime.datetime.now(tz=datetime.timezone.utc)
        date = departure_datetime.strftime("%Y%m%d")
        time = departure_datetime.strftime("%H%M")
        parameters["date"] = date
        parameters["time"] = time
        parameters["timeIs"] = "departing"
    else:
        arrival_datetime = arrival_datetime.astimezone(datetime.timezone.utc)
        date = arrival_datetime.strftime("%Y%m%d")
        time = arrival_datetime.strftime("%H%M")
        parameters["date"] = date
        parameters["time"] = time
        parameters["timeIs"] = "arriving"
    return parameters


def get_next_datetime(arrival_time: datetime.time) -> datetime.datetime:
    if arrival_time.tzinfo is None:
        raise ValueError("arrival_time must be timezone-aware")
    next_day = datetime.datetime.now(
        tz=arrival_time.tzinfo
    ).date() + datetime.timedelta(days=1)
    while next_day.weekday() > 4:
        next_day = next_day + datetime.timedelta(days=1)
    return datetime.datetime(
        next_day.year,
        next_day.month,
        next_day.day,
        hour=arrival_time.hour,
        minute=arrival_time.minute,
        second=arrival_time.second,
        microsecond=arrival_time.microsecond,
        tzinfo=arrival_time.tzinfo,
    )
