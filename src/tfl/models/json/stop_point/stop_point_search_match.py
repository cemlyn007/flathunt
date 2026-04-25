"""Pydantic model for a single stop point search match."""

import pydantic

from tfl.models.json.common.base import TflModel


class StopPointSearchMatch(TflModel):
    """A single match from a stop point search."""

    type: str = pydantic.Field(alias="$type")
    ics_id: str | None = None
    modes: list[str] = pydantic.Field(default_factory=list)
    zone: str | None = None
    id: str
    name: str
    lat: float
    lon: float
    url: str | None = None
    top_most_parent_id: str | None = None
