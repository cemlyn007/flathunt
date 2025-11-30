import datetime
import enum

import pydantic


class Place(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    url: str
    common_name: str = pydantic.Field(alias="commonName")
    place_type: str = pydantic.Field(alias="placeType")
    additional_properties: list = pydantic.Field(alias="additionalProperties")
    lat: float
    lon: float


class DisambiguationOption(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    parameter_value: str = pydantic.Field(alias="parameterValue")
    uri: str
    place: Place
    match_quality: int = pydantic.Field(alias="matchQuality")


class Disambiguation(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    disambiguation_options: list[DisambiguationOption] | None = pydantic.Field(
        default=None, alias="disambiguationOptions"
    )
    match_status: str = pydantic.Field(alias="matchStatus")


class DisambiguationResult(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    to_location_disambiguation: Disambiguation = pydantic.Field(
        alias="toLocationDisambiguation"
    )
    from_location_disambiguation: Disambiguation = pydantic.Field(
        alias="fromLocationDisambiguation"
    )
    via_location_disambiguation: Disambiguation = pydantic.Field(
        alias="viaLocationDisambiguation"
    )
    recommended_max_age_minutes: int = pydantic.Field(alias="recommendedMaxAgeMinutes")
    search_criteria: "SearchCriteria" = pydantic.Field(alias="searchCriteria")
    journey_vector: "JourneyVector" = pydantic.Field(alias="journeyVector")


class PathAttribute(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")


class InstructionStep(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    description: str
    turn_direction: str = pydantic.Field(alias="turnDirection")
    street_name: str = pydantic.Field(alias="streetName")
    distance: int
    cumulative_distance: int = pydantic.Field(alias="cumulativeDistance")
    sky_direction: int = pydantic.Field(alias="skyDirection")
    sky_direction_description: str = pydantic.Field(alias="skyDirectionDescription")
    cumulative_travel_time: int = pydantic.Field(alias="cumulativeTravelTime")
    latitude: float
    longitude: float
    path_attribute: PathAttribute = pydantic.Field(alias="pathAttribute")
    description_heading: str = pydantic.Field(alias="descriptionHeading")
    track_type: str = pydantic.Field(alias="trackType")
    travel_time: int = pydantic.Field(alias="travelTime")


class Instruction(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    summary: str
    detailed: str
    steps: list[InstructionStep]


class Point(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    lat: float
    lon: float


class StopPoint(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    name: str | None = None
    ics_code: str | None = pydantic.Field(default=None, alias="icsCode")
    top_most_parent_id: str | None = pydantic.Field(
        default=None, alias="topMostParentId"
    )
    modes: list[str] | None = None
    stop_letter: str | None = pydantic.Field(default=None, alias="stopLetter")
    common_name: str = pydantic.Field(alias="commonName")


class RouteOption(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    name: str
    directions: list[str]
    line_identifier: dict | None = pydantic.Field(default=None, alias="lineIdentifier")


class Fare(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    total_cost: int = pydantic.Field(alias="totalCost")
    fares: list
    caveats: list


class Obstacle(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    obstacle_type: str = pydantic.Field(alias="type")
    incline: str
    stop_id: int = pydantic.Field(alias="stopId")
    position: str


class Path(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    line_string: str = pydantic.Field(alias="lineString")
    stop_points: list = pydantic.Field(alias="stopPoints")
    elevation: list


class ModeId(str, enum.Enum):
    BUS = "bus"
    CABLE_CAR = "cable-car"
    COACH = "coach"
    CYCLE = "cycle"
    CYCLE_HIRE = "cycle-hire"
    DLR = "dlr"
    ELIZABETH_LINE = "elizabeth-line"
    INTERCHANGE_KEEP_SITTING = "interchange-keep-sitting"
    INTERCHANGE_SECURE = "interchange-secure"
    NATIONAL_RAIL = "national-rail"
    OVERGROUND = "overground"
    REPLACEMENT_BUS = "replacement-bus"
    RIVER_BUS = "river-bus"
    RIVER_TOUR = "river-tour"
    TAXI = "taxi"
    TRAM = "tram"
    TUBE = "tube"
    WALKING = "walking"


class Mode(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    id: ModeId
    name: str
    mode_type: str = pydantic.Field(alias="type")
    route_type: str = pydantic.Field(alias="routeType")
    status: str
    mot_type: str = pydantic.Field(alias="motType")
    network: str


class Leg(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    duration: int
    instruction: Instruction
    obstacles: list[Obstacle]
    departure_time: pydantic.AwareDatetime = pydantic.Field(alias="departureTime")
    arrival_time: pydantic.AwareDatetime = pydantic.Field(alias="arrivalTime")
    departure_point: StopPoint = pydantic.Field(alias="departurePoint")
    arrival_point: StopPoint = pydantic.Field(alias="arrivalPoint")
    path: Path
    route_options: list[RouteOption] = pydantic.Field(alias="routeOptions")
    mode: Mode
    disruptions: list
    planned_works: list = pydantic.Field(alias="plannedWorks")
    distance: float | None = None
    is_disrupted: bool = pydantic.Field(alias="isDisrupted")
    has_fixed_locations: bool = pydantic.Field(alias="hasFixedLocations")
    scheduled_departure_time: pydantic.AwareDatetime = pydantic.Field(
        alias="scheduledDepartureTime"
    )
    scheduled_arrival_time: pydantic.AwareDatetime = pydantic.Field(
        alias="scheduledArrivalTime"
    )
    inter_change_duration: str | None = pydantic.Field(
        default=None, alias="interChangeDuration"
    )
    inter_change_position: str | None = pydantic.Field(
        default=None, alias="interChangePosition"
    )

    @pydantic.field_validator(
        "departure_time",
        "arrival_time",
        "scheduled_departure_time",
        "scheduled_arrival_time",
        mode="before",
    )
    @classmethod
    def add_timezone(cls, v: str | datetime.datetime) -> datetime.datetime:
        if isinstance(v, str):
            dt = datetime.datetime.fromisoformat(v)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        return v


class Journey(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    start_date_time: pydantic.AwareDatetime = pydantic.Field(alias="startDateTime")
    duration: int
    arrival_date_time: pydantic.AwareDatetime = pydantic.Field(alias="arrivalDateTime")
    alternative_route: bool = pydantic.Field(alias="alternativeRoute")
    legs: list[Leg]
    fare: Fare | None = None

    @pydantic.field_validator("start_date_time", "arrival_date_time", mode="before")
    @classmethod
    def add_timezone(cls, v: str | datetime.datetime) -> datetime.datetime:
        if isinstance(v, str):
            dt = datetime.datetime.fromisoformat(v)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        return v


class SearchCriteria(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    date_time: pydantic.AwareDatetime = pydantic.Field(alias="dateTime")
    date_time_type: str = pydantic.Field(alias="dateTimeType")

    @pydantic.field_validator("date_time", mode="before")
    @classmethod
    def add_timezone(cls, v: str | datetime.datetime) -> datetime.datetime:
        if isinstance(v, str):
            dt = datetime.datetime.fromisoformat(v)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        return v


class JourneyVector(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    from_location: str = pydantic.Field(alias="from")
    to_location: str = pydantic.Field(alias="to")
    via: str
    uri: str


class Crowding(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")


class LineServiceTypeInfo(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    name: str
    uri: str


class ValidityPeriod(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")


class LineStatus(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    id: int
    status_severity: int = pydantic.Field(alias="statusSeverity")
    status_severity_description: str = pydantic.Field(alias="statusSeverityDescription")
    created: pydantic.AwareDatetime
    validity_periods: list[ValidityPeriod] = pydantic.Field(alias="validityPeriods")

    @pydantic.field_validator("created", mode="before")
    @classmethod
    def add_timezone(cls, v: str | datetime.datetime) -> datetime.datetime:
        if isinstance(v, str):
            dt = datetime.datetime.fromisoformat(v)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        return v


class Line(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    id: str
    name: str
    mode_name: str = pydantic.Field(alias="modeName")
    disruptions: list
    created: pydantic.AwareDatetime
    modified: pydantic.AwareDatetime
    line_statuses: list[LineStatus] = pydantic.Field(alias="lineStatuses")
    route_sections: list = pydantic.Field(alias="routeSections")
    service_types: list[LineServiceTypeInfo] = pydantic.Field(alias="serviceTypes")
    crowding: Crowding

    @pydantic.field_validator("created", "modified", mode="before")
    @classmethod
    def add_timezone(cls, v: str | datetime.datetime) -> datetime.datetime:
        if isinstance(v, str):
            dt = datetime.datetime.fromisoformat(v)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        return v


class JourneyResults(pydantic.BaseModel):
    type: str = pydantic.Field(alias="$type")
    journeys: list[Journey]
    lines: list[Line]
    stop_messages: list = pydantic.Field(alias="stopMessages")
    recommended_max_age_minutes: int = pydantic.Field(alias="recommendedMaxAgeMinutes")
    search_criteria: SearchCriteria = pydantic.Field(alias="searchCriteria")
    journey_vector: JourneyVector = pydantic.Field(alias="journeyVector")
