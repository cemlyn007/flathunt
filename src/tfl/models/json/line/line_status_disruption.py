"""Disruption details within a line status."""

import pydantic

from tfl.models.json.common.base import TflModel


class LineStatusDisruption(TflModel):
    """Disruption details within a line status."""

    type: str = pydantic.Field(alias="$type")
    category: str | None = None
    category_description: str | None = None
    description: str | None = None
    additional_info: str | None = None
    created: str | None = None
    last_update: str | None = None
