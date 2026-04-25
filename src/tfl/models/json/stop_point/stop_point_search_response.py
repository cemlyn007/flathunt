"""Pydantic model for stop point search response."""

import pydantic

from tfl.models.json.common.base import TflModel
from tfl.models.json.stop_point.stop_point_search_match import StopPointSearchMatch


class StopPointSearchResponse(TflModel):
    """Response from a stop point search query."""

    type: str = pydantic.Field(alias="$type")
    query: str
    total: int
    matches: list[StopPointSearchMatch] = pydantic.Field(default_factory=list)
