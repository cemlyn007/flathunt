"""Crowding information for a TfL line."""

import pydantic

from tfl.models.base import TflModel


class LineCrowding(TflModel):
    """Crowding information for a line."""

    type: str = pydantic.Field(alias="$type")
