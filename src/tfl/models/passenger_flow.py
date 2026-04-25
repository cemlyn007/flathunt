from __future__ import annotations

import pydantic

from tfl.models.base import TflModel


class PassengerFlow(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    time_slice: str
    value: int
