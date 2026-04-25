from __future__ import annotations

import pydantic

from tfl.models.base import TflModel
from tfl.models.schedule import Schedule
from tfl.models.station_interval import StationInterval


class TimetableRoute(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    station_intervals: list[StationInterval]
    schedules: list[Schedule]
