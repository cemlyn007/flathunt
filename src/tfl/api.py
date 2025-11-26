import datetime
import urllib.parse
from typing import Any, Optional, Union

import httpx
from httpx_limiter.async_rate_limited_transport import AsyncRateLimitedTransport
from httpx_limiter.rate import Rate

from tfl import models


class Tfl:
    def __init__(
        self,
        app_key: str,
    ) -> None:
        self._app_key = app_key

    async def get_journey_results(
        self,
        from_location: Union[tuple[float, float], str],
        to_location: tuple[float, float],
        arrival_datetime: Optional[datetime.datetime] = None,
    ) -> models.JourneyResults:
        return await get_journey_results(
            from_location,
            to_location,
            arrival_datetime,
            app_key=self._app_key,
        )


async def get_journey_results(
    from_location: Union[tuple[float, float], str],
    to_location: tuple[float, float],
    arrival_datetime: Optional[datetime.datetime],
    app_key: str,
) -> models.JourneyResults:
    url = build_journey_url(from_location, to_location)
    parameters = build_journey_parameters(arrival_datetime, app_key)
    response_data = await get(url, parameters)
    return models.JourneyResults.model_validate_json(response_data)


async def get(url: str, parameters: dict[str, Any]) -> bytes:
    async with httpx.AsyncClient(
        base_url="https://api.tfl.gov.uk",
        transport=AsyncRateLimitedTransport.create(
            Rate.create(magnitude=1, duration=1.0 / 500.0)
        ),
    ) as client:
        response = await client.get(url, params=parameters)
        response.raise_for_status()
    return response.content


def build_journey_url(
    from_location: tuple[float, float] | str, to_location: tuple[float, float]
) -> str:
    from_location_encoded = urllib.parse.quote(
        from_location
        if isinstance(from_location, str)
        else ",".join(map(str, from_location))
    )
    to_location_encoded = urllib.parse.quote(",".join(map(str, to_location)))
    url = f"/Journey/JourneyResults/{from_location_encoded}/to/{to_location_encoded}"
    return url


def build_journey_parameters(arrival_datetime: datetime.datetime | None, app_key: str):
    parameters = {
        "app_key": app_key,
        "mode": ",".join(mode.value for mode in models.ModeId),
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
