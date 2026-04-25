from __future__ import annotations

import pydantic

from tfl.models.json.common.base import TflModel
from tfl.models.json.timetable.known_journey import KnownJourney
from tfl.models.json.timetable.period import Period


class Schedule(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    name: str
    known_journeys: list[KnownJourney]
    first_journey: KnownJourney | None = None
    last_journey: KnownJourney | None = None
    periods: list[Period] | None = None
