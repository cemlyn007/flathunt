import pydantic

from tfl.models.base import TflModel


class RouteSection(TflModel):
    type: str | None = pydantic.Field(default=None, alias="$type")
    name: str | None = None
    direction: str | None = None
    origination_name: str | None = None
    destination_name: str | None = None
    originator: str | None = None
    destination: str | None = None
    route_code: str | None = None
    line_string: str | None = None
    valid_to: str | None = None
    valid_from: str | None = None
