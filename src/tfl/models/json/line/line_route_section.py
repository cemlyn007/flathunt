"""Route section information for a TfL line."""

import pydantic

from tfl.models.json.common.base import TflModel


class LineRouteSection(TflModel):
    """Route section information for a line."""

    type: str | None = pydantic.Field(default=None, alias="$type")
    name: str | None = None
    direction: str | None = None
    origination_name: str | None = None
    destination_name: str | None = None
    originator: str | None = None
    destination: str | None = None
    service_type: str | None = None
    valid_to: str | None = None
    valid_from: str | None = None
