import http.client
import gzip
import json
from typing import Any
import enum
import http
import typing
import urllib.parse
import datetime
import zoneinfo

TIMEZONE = zoneinfo.ZoneInfo("Europe/London")


class HTTPError(Exception): ...


class Mode(enum.StrEnum):
    BUS = "bus"
    TUBE = "tube"
    WALKING = "walking"


class Journey(typing.NamedTuple):
    duration: datetime.timedelta
    departure_datetime: datetime.datetime
    arrival_datetime: datetime.datetime
    mode: Mode
    route_name: str


class Tfl:
    def __init__(
        self,
        from_location: tuple[float, float],
        to_location: tuple[float, float],
        app_key: str,
        arrival_datetime: datetime.datetime | None = None,
    ) -> None:
        self._from_location = from_location
        self._to_location = to_location
        self._app_key = app_key
        self._arrival_datetime = arrival_datetime

    def __call__(self) -> list[Journey]:
        response = get_journey_options(
            self._from_location,
            self._to_location,
            self._arrival_datetime,
            app_key=self._app_key,
        )
        raw_journeys = response["journeys"]
        journeys = [
            parse_journey(raw_journey, datetime.UTC) for raw_journey in raw_journeys
        ]
        arrival_datetime = self._arrival_datetime
        if arrival_datetime is None:
            journeys.sort(key=lambda journey: journey.arrival_datetime.timestamp())
        else:
            journeys.sort(
                key=lambda journey: arrival_datetime.timestamp()
                - journey.arrival_datetime.timestamp()
            )
        return journeys


def get_journey_options(
    from_location: tuple[float, float],
    to_location: tuple[float, float],
    arrival_datetime: datetime.datetime | None,
    app_key: str,
) -> Any:
    from_location_encoded = urllib.parse.quote(",".join(map(str, from_location)))
    to_location_encoded = urllib.parse.quote(",".join(map(str, to_location)))
    url = f"/Journey/JourneyResults/{from_location_encoded}/to/{to_location_encoded}"
    parameters = {
        "app_key": app_key,
        "mode": "bus",
    }
    if arrival_datetime is None:
        departure_datetime = datetime.datetime.now(
            tz=zoneinfo.ZoneInfo("Europe/London")
        )
        date = departure_datetime.strftime("%Y%m%d")
        time = departure_datetime.strftime("%H%M")
        parameters["date"] = date
        parameters["time"] = time
        parameters["timeIs"] = "departing"

    connection = http.client.HTTPSConnection("api.tfl.gov.uk", port=443)
    try:
        response = _request(connection, "GET", url, parameters)
    finally:
        connection.close()
    return response


def parse_journey(journey: dict[str, Any], time_zone: datetime.timezone) -> Journey:
    duration_minutes = int(journey["duration"])
    departure_datetime = (
        datetime.datetime.strptime(journey["startDateTime"], "%Y-%m-%dT%H:%M:%S")
        .replace(tzinfo=time_zone)
        .astimezone(time_zone)
    )
    arrival_datetime = (
        datetime.datetime.strptime(journey["arrivalDateTime"], "%Y-%m-%dT%H:%M:%S")
        .replace(tzinfo=time_zone)
        .astimezone(time_zone)
    )
    modes = [Mode(leg["mode"]["id"]) for leg in journey["legs"]]
    if Mode.TUBE in modes:
        mode = Mode.TUBE
    elif Mode.BUS in modes:
        mode = Mode.BUS
    else:
        mode = Mode.WALKING
    route_names = []
    for leg in journey["legs"]:
        if "routeOptions" in leg:
            name = next(option["name"] for option in leg["routeOptions"])
            if name:
                route_names.append(name)
    route_name = "->".join(route_names)
    return Journey(
        duration=datetime.timedelta(minutes=duration_minutes),
        departure_datetime=departure_datetime,
        arrival_datetime=arrival_datetime,
        mode=mode,
        route_name=route_name,
    )


def get_next_datetime(
    arrival_time: datetime.time, timezone: datetime.tzinfo = TIMEZONE
) -> datetime.datetime:
    next_day = datetime.datetime.now(tz=timezone).date() + datetime.timedelta(days=1)
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
        tzinfo=timezone,
    )


def _request(
    connection: http.client.HTTPSConnection,
    method: str,
    url: str,
    parameters: dict[str, Any],
) -> Any:
    query_string = urllib.parse.urlencode(parameters, doseq=True)
    urlparse = urllib.parse.urlparse(url)
    urlparse = urlparse._replace(query=query_string)
    url = urllib.parse.urlunparse(urlparse)
    connection.request(
        method,
        url,
        headers={
            "User-Agent": "IAmLookingToRent/0.0.0",
            "Accept-Encoding": "gzip",
            "Accept": "*/*",
            "Connection": "keep-alive",
        },
    )
    http_response = connection.getresponse()
    if http_response.status != http.HTTPStatus.OK:
        raise HTTPError(f"HTTP error {http_response.status}: {http_response.reason}")
    raw_response = http_response.read()
    if http_response.getheader("Content-Encoding") == "gzip":
        raw_response = gzip.decompress(raw_response)
    response = json.loads(raw_response)
    return response
