from __future__ import annotations

import pydantic

from tfl.models.base import TflModel


class TimetableDisambiguationOption(TflModel):
    tfl_type: str | None = pydantic.Field(default=None, alias="$type")
    description: str
    uri: str
