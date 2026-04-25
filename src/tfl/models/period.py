from __future__ import annotations

import pydantic

from tfl.models.base import TflModel
from tfl.models.service_frequency import ServiceFrequency
from tfl.models.twenty_four_hour_clock_time import TwentyFourHourClockTime


class Period(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    type: str
    from_time: TwentyFourHourClockTime
    to_time: TwentyFourHourClockTime
    frequency: ServiceFrequency | None = None
