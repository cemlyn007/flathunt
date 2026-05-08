import pydantic

from tfl.models.json.common.base import TflModel


class Path(TflModel):
    type: str = pydantic.Field(alias="$type")
    line_string: str
    stop_points: list
    elevation: list
