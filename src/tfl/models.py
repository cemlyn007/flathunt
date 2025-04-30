import enum
import datetime
import pydantic


class Mode(enum.Enum):
    BUS = "bus"
    TUBE = "tube"
    WALKING = "walking"


class Journey(pydantic.BaseModel, frozen=True):
    duration: datetime.timedelta
    departure_datetime: pydantic.AwareDatetime
    arrival_datetime: pydantic.AwareDatetime
    mode: Mode
    route_name: str
