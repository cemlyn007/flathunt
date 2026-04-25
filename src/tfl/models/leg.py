import datetime

import pydantic

from tfl.models.base import TflModel
from tfl.models.instruction import Instruction
from tfl.models.mode import Mode
from tfl.models.obstacle import Obstacle
from tfl.models.path_journey import Path
from tfl.models.route_option import RouteOption
from tfl.models.stop_point_journey import StopPoint


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
                return dt.replace(tzinfo=datetime.UTC)
            return dt
        return v
