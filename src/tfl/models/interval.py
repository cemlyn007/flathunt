from __future__ import annotations

import pydantic

from tfl.models.base import TflModel


class Interval(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    stop_id: str
    time_to_arrival: float
