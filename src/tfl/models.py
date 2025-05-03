import enum
import datetime
import pydantic


class Mode(enum.Enum):
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


class Journey(pydantic.BaseModel, frozen=True):
    duration: datetime.timedelta
    departure_datetime: pydantic.AwareDatetime
    arrival_datetime: pydantic.AwareDatetime
    mode: Mode
    route_name: str
