import pydantic

from tfl.models.base import TflModel


class PathAttribute(TflModel):
    type: str = pydantic.Field(alias="$type")
