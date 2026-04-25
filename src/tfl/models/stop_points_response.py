"""Pydantic model for stop points response."""

import pydantic

from tfl.models.base import TflModel
from tfl.models.stop_point_detail import StopPointDetail


class StopPointsResponse(TflModel):
    """Response containing a list of stop points."""

    type: str = pydantic.Field(alias="$type")
    stop_points: list[StopPointDetail] = pydantic.Field(default_factory=list)
    page_size: int | None = None
    total: int | None = None
    page: int | None = None
