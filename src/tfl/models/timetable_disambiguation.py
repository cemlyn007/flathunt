from __future__ import annotations

import pydantic

from tfl.models.base import TflModel
from tfl.models.timetable_disambiguation_option import TimetableDisambiguationOption


class TimetableDisambiguation(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    disambiguation_options: list[TimetableDisambiguationOption] | None = None
