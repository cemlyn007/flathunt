"""Pydantic model for line information in a stop point."""

from typing import Literal

import pydantic

from tfl.models.json.common.base import TflModel


class StopPointLine(TflModel):
    """Line information for a stop point."""

    type: str | None = pydantic.Field(default=None, alias="$type")
    line_type: str | None = pydantic.Field(default=None, alias="type")
    route_type: str | None = None
    status: Literal["Unknown"] | None = None
    id: str
    name: str
    uri: str
    full_name: str | None = None
    mode_name: str | None = None
    disruptions: list = pydantic.Field(default_factory=list)
    created: str | None = None
    modified: str | None = None
    line_statuses: list = pydantic.Field(default_factory=list)
    route_sections: list = pydantic.Field(default_factory=list)
    service_types: list = pydantic.Field(default_factory=list)
    crowding: dict | None = None
