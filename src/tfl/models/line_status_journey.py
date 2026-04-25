import datetime

import pydantic

from tfl.models.base import TflModel
from tfl.models.disruption import Disruption
from tfl.models.validity_period import ValidityPeriod


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
                return dt.replace(tzinfo=datetime.UTC)
            return dt
        return v
