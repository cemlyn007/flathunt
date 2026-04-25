from __future__ import annotations

import pydantic

from tfl.models.json.common.base import TflModel
from tfl.models.json.timetable.interval import Interval


class StationInterval(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    id: str
    intervals: list[Interval]
