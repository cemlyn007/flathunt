from __future__ import annotations

import pydantic

from tfl.models.json.common.base import TflModel
from tfl.models.json.timetable.timetable_route import TimetableRoute


class Timetable(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    departure_stop_id: str
    routes: list[TimetableRoute]
