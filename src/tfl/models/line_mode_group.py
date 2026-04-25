"""Pydantic model for line mode group information."""

import pydantic

from tfl.models.base import TflModel


class LineModeGroup(TflModel):
    """Line mode group information."""

    type: str | None = pydantic.Field(default=None, alias="$type")
    mode_name: str
    line_identifier: list[str] = pydantic.Field(default_factory=list)
