from __future__ import annotations

import pydantic

from tfl.models.json.common.base import TflModel


class TwentyFourHourClockTime(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    hour: str
    minute: str
