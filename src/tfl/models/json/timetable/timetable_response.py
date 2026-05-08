from __future__ import annotations

import pydantic

from tfl.models.json.common.base import TflModel
from tfl.models.json.timetable.station_stop import StationStop
from tfl.models.json.timetable.timetable_disambiguation import TimetableDisambiguation
from tfl.models.json.timetable.timetable_model import Timetable


class TimetableResponse(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    type: str | None = None
    line_id: str | None = None
    line_name: str | None = None
    direction: str | None = None
    pdf_url: str | None = None
    stations: list[StationStop] | None = None
    stops: list[StationStop] | None = None
    timetable: Timetable | None = None
    disambiguation: TimetableDisambiguation | None = None
    status_error_message: str | None = None
