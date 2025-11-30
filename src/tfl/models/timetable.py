from __future__ import annotations

import pydantic


class PassengerFlow(pydantic.BaseModel):
    time_slice: str = pydantic.Field(alias="timeSlice")
    value: int


class TrainLoading(pydantic.BaseModel):
    line: str
    line_direction: str = pydantic.Field(alias="lineDirection")
    platform_direction: str = pydantic.Field(alias="platformDirection")
    direction: str
    naptan_to: str = pydantic.Field(alias="naptanTo")
    time_slice: str = pydantic.Field(alias="timeSlice")
    value: int


class Crowding(pydantic.BaseModel):
    passenger_flows: list[PassengerFlow] | None = pydantic.Field(
        default=None, alias="passengerFlows"
    )
    train_loadings: list[TrainLoading] | None = pydantic.Field(
        default=None, alias="trainLoadings"
    )


class LineInfo(pydantic.BaseModel):
    id: str
    name: str
    uri: str
    full_name: str | None = pydantic.Field(default=None, alias="fullName")
    type: str
    crowding: Crowding | None = None
    route_type: str | None = pydantic.Field(default=None, alias="routeType")
    status: str | None = None
    mot_type: str | None = pydantic.Field(default=None, alias="motType")
    network: str | None = None


class StationStop(pydantic.BaseModel):
    route_id: int | None = pydantic.Field(default=None, alias="routeId")
    parent_id: str | None = pydantic.Field(default=None, alias="parentId")
    station_id: str | None = pydantic.Field(default=None, alias="stationId")
    ics_id: str | None = pydantic.Field(default=None, alias="icsId")
    top_most_parent_id: str | None = pydantic.Field(
        default=None, alias="topMostParentId"
    )
    direction: str | None = None
    towards: str | None = None
    modes: list[str] | None = None
    stop_type: str | None = pydantic.Field(default=None, alias="stopType")
    stop_letter: str | None = pydantic.Field(default=None, alias="stopLetter")
    zone: str | None = None
    accessibility_summary: str | None = pydantic.Field(
        default=None, alias="accessibilitySummary"
    )
    has_disruption: bool | None = pydantic.Field(default=None, alias="hasDisruption")
    lines: list[LineInfo] | None = None
    status: bool | None = None
    id: str
    url: str | None = None
    name: str
    lat: float
    lon: float


class Interval(pydantic.BaseModel):
    stop_id: str = pydantic.Field(alias="stopId")
    time_to_arrival: float = pydantic.Field(alias="timeToArrival")


class StationInterval(pydantic.BaseModel):
    id: str
    intervals: list[Interval]


class KnownJourney(pydantic.BaseModel):
    hour: str
    minute: str
    interval_id: int = pydantic.Field(alias="intervalId")


class TwentyFourHourClockTime(pydantic.BaseModel):
    hour: str
    minute: str


class ServiceFrequency(pydantic.BaseModel):
    lowest_frequency: float = pydantic.Field(alias="lowestFrequency")
    highest_frequency: float = pydantic.Field(alias="highestFrequency")


class Period(pydantic.BaseModel):
    type: str
    from_time: TwentyFourHourClockTime = pydantic.Field(alias="fromTime")
    to_time: TwentyFourHourClockTime = pydantic.Field(alias="toTime")
    frequency: ServiceFrequency | None = None


class Schedule(pydantic.BaseModel):
    name: str
    known_journeys: list[KnownJourney] = pydantic.Field(alias="knownJourneys")
    first_journey: KnownJourney | None = pydantic.Field(
        default=None, alias="firstJourney"
    )
    last_journey: KnownJourney | None = pydantic.Field(
        default=None, alias="lastJourney"
    )
    periods: list[Period] | None = None


class TimetableRoute(pydantic.BaseModel):
    station_intervals: list[StationInterval] = pydantic.Field(alias="stationIntervals")
    schedules: list[Schedule]


class Timetable(pydantic.BaseModel):
    departure_stop_id: str = pydantic.Field(alias="departureStopId")
    routes: list[TimetableRoute]


class TimetableDisambiguationOption(pydantic.BaseModel):
    description: str
    uri: str


class TimetableDisambiguation(pydantic.BaseModel):
    disambiguation_options: list[TimetableDisambiguationOption] | None = pydantic.Field(
        default=None, alias="disambiguationOptions"
    )


class TimetableResponse(pydantic.BaseModel):
    type: str | None = pydantic.Field(default=None, alias="$type")
    line_id: str | None = pydantic.Field(default=None, alias="lineId")
    line_name: str | None = pydantic.Field(default=None, alias="lineName")
    direction: str | None = None
    pdf_url: str | None = pydantic.Field(default=None, alias="pdfUrl")
    stations: list[StationStop] | None = None
    stops: list[StationStop] | None = None
    timetable: Timetable | None = None
    disambiguation: TimetableDisambiguation | None = None
    status_error_message: str | None = pydantic.Field(
        default=None, alias="statusErrorMessage"
    )
