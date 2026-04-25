"""A TfL line model (e.g., a tube line like Bakerloo, Central, etc.)."""

import pydantic

from tfl.models.base import TflModel
from tfl.models.line_crowding import LineCrowding
from tfl.models.line_disruption import LineDisruption
from tfl.models.line_route_section import LineRouteSection
from tfl.models.line_service_type import LineServiceType
from tfl.models.line_status import LineStatus
from tfl.models.matched_route import MatchedRoute
from tfl.models.mode_id import ModeId


class Line(TflModel):
    """A TfL line (e.g., a tube line like Bakerloo, Central, etc.)."""

    type: str = pydantic.Field(alias="$type")
    id: str
    name: str
    mode_name: ModeId
    disruptions: list[LineDisruption] = pydantic.Field(default_factory=list)
    created: str
    modified: str
    line_statuses: list[LineStatus] = pydantic.Field(default_factory=list)
    route_sections: list[MatchedRoute | LineRouteSection] = pydantic.Field(
        default_factory=list
    )
    service_types: list[LineServiceType] = pydantic.Field(default_factory=list)
    crowding: LineCrowding | None = None


# Type adapter for parsing an array of Line directly
LineList = pydantic.TypeAdapter(list[Line])

# Type adapter for parsing the /Line/Route endpoint response
LinesRoutesResponse = pydantic.TypeAdapter(list[Line])
