from __future__ import annotations

import pydantic

from tfl.models.base import TflModel
from tfl.models.interval import Interval


class StationInterval(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    id: str
    intervals: list[Interval]
