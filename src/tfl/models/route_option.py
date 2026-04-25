import pydantic

from tfl.models.base import TflModel


class RouteOption(TflModel):
    type: str = pydantic.Field(alias="$type")
    name: str
    directions: list[str]
    direction: str | None = None
    line_identifier: dict | None = None
