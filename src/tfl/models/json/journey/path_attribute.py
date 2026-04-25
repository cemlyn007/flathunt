import pydantic

from tfl.models.json.common.base import TflModel


class PathAttribute(TflModel):
    type: str = pydantic.Field(alias="$type")
