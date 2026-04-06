from __future__ import annotations

import pydantic

from tfl.models.base import TflModel


class PassengerFlow(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    time_slice: str
    value: int


class TrainLoading(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    line: str
    line_direction: str
    platform_direction: str
    direction: str
    naptan_to: str
    time_slice: str
    value: int


class Crowding(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    passenger_flows: list[PassengerFlow] | None = None
    train_loadings: list[TrainLoading] | None = None


class LineInfo(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    id: str
    name: str
    uri: str
    full_name: str | None = None
    type: str
    crowding: Crowding | None = None
    route_type: str | None = None
    status: str | None = None
    mot_type: str | None = None
    network: str | None = None


class StationStop(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    route_id: int | None = None
    parent_id: str | None = None
    station_id: str | None = None
    ics_id: str | None = None
    top_most_parent_id: str | None = None
    direction: str | None = None
    towards: str | None = None
    modes: list[str] | None = None
    stop_type: str | None = None
    stop_letter: str | None = None
    zone: str | None = None
    accessibility_summary: str | None = None
    has_disruption: bool | None = None
    lines: list[LineInfo] | None = None
    status: bool | None = None
    id: str
    url: str | None = None
    name: str
    lat: float
    lon: float


class Interval(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    stop_id: str
    time_to_arrival: float


class StationInterval(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    id: str
    intervals: list[Interval]


class KnownJourney(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    hour: str
    minute: str
    interval_id: int


class TwentyFourHourClockTime(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    hour: str
    minute: str


class ServiceFrequency(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    lowest_frequency: float
    highest_frequency: float


class Period(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    type: str
    from_time: TwentyFourHourClockTime
    to_time: TwentyFourHourClockTime
    frequency: ServiceFrequency | None = None


class Schedule(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    name: str
    known_journeys: list[KnownJourney]
    first_journey: KnownJourney | None = None
    last_journey: KnownJourney | None = None
    periods: list[Period] | None = None


class TimetableRoute(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    station_intervals: list[StationInterval]
    schedules: list[Schedule]


class Timetable(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    departure_stop_id: str
    routes: list[TimetableRoute]


class TimetableDisambiguationOption(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    description: str
    uri: str


class TimetableDisambiguation(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    disambiguation_options: list[TimetableDisambiguationOption] | None = None


class TimetableResponse(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    type: str | None = None
    line_id: str | None = None
    line_name: str | None = None
    direction: str | None = None
    pdf_url: str | None = None
    stations: list[StationStop] | None = None
    stops: list[StationStop] | None = None
    timetable: Timetable | None = None
    disambiguation: TimetableDisambiguation | None = None
    status_error_message: str | None = None
