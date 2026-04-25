from __future__ import annotations

import pydantic

from tfl.models.json.common.base import TflModel


class TrainLoading(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    line: str
    line_direction: str
    platform_direction: str
    direction: str
    naptan_to: str
    time_slice: str
    value: int
