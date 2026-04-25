import datetime

import pydantic

from tfl.models.base import TflModel
from tfl.models.fare import Fare
from tfl.models.leg import Leg


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
                return dt.replace(tzinfo=datetime.UTC)
            return dt
        return v
