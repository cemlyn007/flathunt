from __future__ import annotations

import pydantic

from tfl.models.base import TflModel
from tfl.models.line_info import LineInfo


class StationStop(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    route_id: int | None = None
    parent_id: str | None = None
    station_id: str | None = None
    ics_id: str | None = None
    top_most_parent_id: str | None = None
    direction: str | None = None
    towards: str | None = None
    modes: list[str] | None = None
    stop_type: str | None = None
    stop_letter: str | None = None
    zone: str | None = None
    accessibility_summary: str | None = None
    has_disruption: bool | None = None
    lines: list[LineInfo] | None = None
    status: bool | None = None
    id: str
    url: str | None = None
    name: str
    lat: float
    lon: float
