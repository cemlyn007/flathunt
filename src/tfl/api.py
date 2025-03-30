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


class HTTPError(Exception): ...


class Mode(enum.StrEnum):
    BUS = "bus"
    TUBE = "tube"
    WALKING = "walking"


class Journey(typing.NamedTuple):
    duration_in_minutes: int
    departure_datetime: datetime.datetime
    arrival_datetime: datetime.datetime
    mode: Mode
    route_name: str


class JourneyApi:
    def __init__(
        self,
        from_location: tuple[float, float],
        to_location: tuple[float, float],
        app_key: str,
        arrival_time: datetime.time | None = None,
    ) -> None:
        self._from_location = from_location
        self._to_location = to_location
        self._app_key = app_key
        self._arrival_time = arrival_time
        self._time_zone = zoneinfo.ZoneInfo("Europe/London")

    def __call__(self) -> Journey | None:
        if self._arrival_time is not None:
            current_datetime = datetime.datetime.now(tz=self._time_zone)
            if current_datetime.time() < datetime.time(hour=9):
                arrival_datetime = current_datetime.replace(
                    hour=self._arrival_time.hour,
                    minute=self._arrival_time.minute,
                    second=self._arrival_time.second,
                    microsecond=self._arrival_time.microsecond,
                )
            else:
                tomorrow = current_datetime.date() + datetime.timedelta(days=1)
                arrival_datetime = datetime.datetime(
                    tomorrow.year,
                    tomorrow.month,
                    tomorrow.day,
                    hour=self._arrival_time.hour,
                    minute=self._arrival_time.minute,
                    second=self._arrival_time.second,
                    microsecond=self._arrival_time.microsecond,
                    tzinfo=self._time_zone,
                )
        else:
            arrival_datetime = None
        response = get_journey(
            self._from_location,
            self._to_location,
            arrival_datetime,
            app_key=self._app_key,
        )
        raw_journeys = response["journeys"]
        journeys = [
            parse_journey(raw_journey, datetime.UTC) for raw_journey in raw_journeys
        ]
        journeys = [
            journey
            for journey in journeys
            if journey is not None and journey.mode == Mode.BUS
        ]
        if arrival_datetime is None:
            journeys.sort(key=lambda journey: journey.arrival_datetime.timestamp())
        else:
            journeys.sort(
                key=lambda journey: (
                    arrival_datetime - journey.arrival_datetime
                ).total_seconds()
            )
        return journeys[0] if journeys else None


def get_journey(
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
    else:
        date = arrival_datetime.strftime("%Y%m%d")
        time = arrival_datetime.strftime("%H%M")
        parameters["date"] = date
        parameters["time"] = time
        parameters["timeIs"] = "arriving"

    connection = http.client.HTTPSConnection("api.tfl.gov.uk", port=443)
    try:
        response = request(connection, "GET", url, parameters)
    finally:
        connection.close()
    return response


def parse_journey(
    journey: dict[str, Any], time_zone: datetime.timezone
) -> Journey | None:
    duration_minutes = int(journey["duration"])
    departure_datetime = (
        datetime.datetime.strptime(
            journey["legs"][0]["departureTime"], "%Y-%m-%dT%H:%M:%S"
        )
        .replace(tzinfo=time_zone)
        .astimezone(time_zone)
    )
    arrival_datetime = (
        datetime.datetime.strptime(journey["arrivalDateTime"], "%Y-%m-%dT%H:%M:%S")
        .replace(tzinfo=time_zone)
        .astimezone(time_zone)
    )
    if len(journey["legs"]) == 1 and journey["legs"][0]["mode"]["id"] == "walking":
        return Journey(
            duration_in_minutes=duration_minutes,
            departure_datetime=departure_datetime,
            arrival_datetime=arrival_datetime,
            mode=Mode.WALKING,
            route_name="",
        )
    elif len(journey["legs"]) != 3:
        return None
    elif journey["legs"][1]["mode"]["id"] != "bus":
        raise ValueError("The middle leg should be a bus journey")
    else:
        route_options = journey["legs"][1]["routeOptions"]
        name = next(route_option["name"] for route_option in route_options)
        return Journey(
            duration_in_minutes=duration_minutes,
            departure_datetime=departure_datetime,
            arrival_datetime=arrival_datetime,
            mode=Mode.BUS,
            route_name=name,
        )


def request(
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
