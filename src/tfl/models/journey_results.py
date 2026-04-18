import datetime
import enum

import pydantic

from tfl.models.base import TflModel


class Place(TflModel):
    type: str = pydantic.Field(alias="$type")
    url: str
    common_name: str
    place_type: str
    additional_properties: list
    lat: float
    lon: float


class DisambiguationOption(TflModel):
    type: str = pydantic.Field(alias="$type")
    parameter_value: str
    uri: str
    place: Place
    match_quality: int


class Disambiguation(TflModel):
    type: str = pydantic.Field(alias="$type")
    disambiguation_options: list[DisambiguationOption] | None = None
    match_status: str


class DisambiguationResult(TflModel):
    type: str = pydantic.Field(alias="$type")
    to_location_disambiguation: Disambiguation
    from_location_disambiguation: Disambiguation
    via_location_disambiguation: Disambiguation
    recommended_max_age_minutes: int
    search_criteria: "SearchCriteria"
    journey_vector: "JourneyVector"


class PathAttribute(TflModel):
    type: str = pydantic.Field(alias="$type")


class InstructionStep(TflModel):
    type: str = pydantic.Field(alias="$type")
    description: str
    turn_direction: str
    street_name: str
    distance: int
    cumulative_distance: int
    sky_direction: int
    sky_direction_description: str
    cumulative_travel_time: int
    latitude: float
    longitude: float
    path_attribute: PathAttribute
    description_heading: str
    track_type: str
    travel_time: int


class Instruction(TflModel):
    type: str = pydantic.Field(alias="$type")
    summary: str
    detailed: str
    steps: list[InstructionStep]


class Point(TflModel):
    type: str = pydantic.Field(alias="$type")
    lat: float
    lon: float


class StopPoint(TflModel):
    type: str = pydantic.Field(alias="$type")
    name: str | None = None
    ics_code: str | None = None
    top_most_parent_id: str | None = None
    modes: list[str] | None = None
    stop_letter: str | None = None
    common_name: str
    platform_name: str | None = None
    place_type: str | None = None
    additional_properties: list = pydantic.Field(default_factory=list)
    lat: float | None = None
    lon: float | None = None
    naptan_id: str | None = None
    individual_stop_id: str | None = None


class RouteSection(TflModel):
    type: str | None = pydantic.Field(default=None, alias="$type")
    name: str | None = None
    direction: str | None = None
    origination_name: str | None = None
    destination_name: str | None = None
    originator: str | None = None
    destination: str | None = None
    route_code: str | None = None
    line_string: str | None = None
    valid_to: str | None = None
    valid_from: str | None = None


class Disruption(TflModel):
    type: str = pydantic.Field(alias="$type")
    category: str | None = None
    category_description: str | None = None
    description: str | None = None
    additional_info: str | None = None
    created: str | None = None
    last_update: str | None = None
    affected_routes: list[RouteSection] = pydantic.Field(default_factory=list)
    affected_stops: list[StopPoint] = pydantic.Field(default_factory=list)
    is_blocking: bool | None = None
    is_whole_line: bool | None = None
    closure_text: str | None = None


class RouteOption(TflModel):
    type: str = pydantic.Field(alias="$type")
    name: str
    directions: list[str]
    direction: str | None = None
    line_identifier: dict | None = None


class Fare(TflModel):
    type: str = pydantic.Field(alias="$type")
    total_cost: int
    fares: list
    caveats: list


class Obstacle(TflModel):
    type: str = pydantic.Field(alias="$type")
    obstacle_type: str = pydantic.Field(alias="type")
    incline: str
    stop_id: int
    position: str


class Path(TflModel):
    type: str = pydantic.Field(alias="$type")
    line_string: str
    stop_points: list
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


class Mode(TflModel):
    type: str = pydantic.Field(alias="$type")
    id: ModeId
    name: str
    mode_type: str = pydantic.Field(alias="type")
    route_type: str
    status: str
    mot_type: str
    network: str


class Leg(TflModel):
    type: str = pydantic.Field(alias="$type")
    duration: int
    instruction: Instruction
    obstacles: list[Obstacle]
    departure_time: pydantic.AwareDatetime
    arrival_time: pydantic.AwareDatetime
    departure_point: StopPoint
    arrival_point: StopPoint
    path: Path
    route_options: list[RouteOption]
    mode: Mode
    disruptions: list
    planned_works: list
    distance: float | None = None
    is_disrupted: bool
    has_fixed_locations: bool
    scheduled_departure_time: pydantic.AwareDatetime
    scheduled_arrival_time: pydantic.AwareDatetime
    inter_change_duration: str | None = None
    inter_change_position: str | None = None

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


class Journey(TflModel):
    type: str = pydantic.Field(alias="$type")
    start_date_time: pydantic.AwareDatetime
    duration: int
    arrival_date_time: pydantic.AwareDatetime
    alternative_route: bool
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


class SearchCriteria(TflModel):
    type: str = pydantic.Field(alias="$type")
    date_time: pydantic.AwareDatetime
    date_time_type: str
    time_adjustments: dict | None = None

    @pydantic.field_validator("date_time", mode="before")
    @classmethod
    def add_timezone(cls, v: str | datetime.datetime) -> datetime.datetime:
        if isinstance(v, str):
            dt = datetime.datetime.fromisoformat(v)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        return v


class JourneyVector(TflModel):
    type: str = pydantic.Field(alias="$type")
    from_location: str = pydantic.Field(alias="from")
    to_location: str = pydantic.Field(alias="to")
    via: str
    uri: str


class Crowding(TflModel):
    type: str = pydantic.Field(alias="$type")


class LineServiceTypeInfo(TflModel):
    type: str = pydantic.Field(alias="$type")
    name: str
    uri: str


class ValidityPeriod(TflModel):
    type: str = pydantic.Field(alias="$type")
    from_date: str | None = None
    to_date: str | None = None
    is_now: bool | None = None


class LineStatus(TflModel):
    type: str = pydantic.Field(alias="$type")
    id: int
    status_severity: int
    status_severity_description: str
    created: pydantic.AwareDatetime
    validity_periods: list[ValidityPeriod]
    line_id: str | None = None
    reason: str | None = None
    disruption: Disruption | None = None

    @pydantic.field_validator("created", mode="before")
    @classmethod
    def add_timezone(cls, v: str | datetime.datetime) -> datetime.datetime:
        if isinstance(v, str):
            dt = datetime.datetime.fromisoformat(v)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        return v


class Line(TflModel):
    type: str = pydantic.Field(alias="$type")
    id: str
    name: str
    mode_name: str
    disruptions: list
    created: pydantic.AwareDatetime
    modified: pydantic.AwareDatetime
    line_statuses: list[LineStatus]
    route_sections: list
    service_types: list[LineServiceTypeInfo]
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


class JourneyResults(TflModel):
    type: str = pydantic.Field(alias="$type")
    journeys: list[Journey]
    lines: list[Line]
    stop_messages: list
    recommended_max_age_minutes: int
    search_criteria: SearchCriteria
    journey_vector: JourneyVector
