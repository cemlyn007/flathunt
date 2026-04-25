from __future__ import annotations

import pydantic

from tfl.models.json.common.base import TflModel
from tfl.models.json.timetable.crowding import Crowding


class LineInfo(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    id: str
    name: str
    uri: str
    full_name: str | None = None
    type: str
    crowding: Crowding | None = None
    route_type: str | None = None
    status: str | None = None
    mot_type: str | None = None
    network: str | None = None
