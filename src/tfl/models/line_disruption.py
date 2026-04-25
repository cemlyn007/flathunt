"""Disruption information for a TfL line."""

import pydantic

from tfl.models.base import TflModel


class LineDisruption(TflModel):
    """Disruption information for a line."""

    type: str = pydantic.Field(alias="$type")
    category: str | None = None
    category_description: str | None = None
    description: str | None = None
    affected_routes: list = pydantic.Field(default_factory=list)
    affected_stops: list = pydantic.Field(default_factory=list)
    closure_text: str | None = None
