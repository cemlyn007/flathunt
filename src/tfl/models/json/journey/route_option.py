import pydantic

from tfl.models.json.common.base import TflModel


class RouteOption(TflModel):
    type: str = pydantic.Field(alias="$type")
    name: str
    directions: list[str]
    direction: str | None = None
    line_identifier: dict | None = None
