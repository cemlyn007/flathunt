"""Pydantic model for line group information."""

import pydantic

from tfl.models.json.common.base import TflModel


class LineGroup(TflModel):
    """Line group information for a stop point."""

    type: str | None = pydantic.Field(default=None, alias="$type")
    naptan_id_reference: str | None = None
    station_atco_code: str | None = None
    line_identifier: list[str] = pydantic.Field(default_factory=list)
