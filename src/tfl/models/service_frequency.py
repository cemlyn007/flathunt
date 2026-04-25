from __future__ import annotations

import pydantic

from tfl.models.base import TflModel


class ServiceFrequency(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    lowest_frequency: float
    highest_frequency: float
