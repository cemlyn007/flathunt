import pydantic

from tfl.models.json.common.base import TflModel
from tfl.models.json.line.route_section import RouteSection
from tfl.models.json.stop_point.stop_point_journey import StopPoint


class Disruption(TflModel):
    type: str = pydantic.Field(alias="$type")
    category: str | None = None
    category_description: str | None = None
    description: str | None = None
    additional_info: str | None = None
    created: str | None = None
    last_update: str | None = None
    affected_routes: list[RouteSection] = pydantic.Field(default_factory=list)
    affected_stops: list[StopPoint] = pydantic.Field(default_factory=list)
    is_blocking: bool | None = None
    is_whole_line: bool | None = None
    closure_text: str | None = None
