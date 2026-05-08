import datetime

import pydantic

from tfl.models.json.common.base import TflModel


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
                return dt.replace(tzinfo=datetime.UTC)
            return dt
        return v
