import datetime

import pydantic

from tfl.models.base import TflModel
from tfl.models.crowding_journey import Crowding
from tfl.models.line_service_type_info import LineServiceTypeInfo
from tfl.models.line_status_journey import LineStatus


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
                return dt.replace(tzinfo=datetime.UTC)
            return dt
        return v
