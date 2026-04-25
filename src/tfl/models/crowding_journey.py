import pydantic

from tfl.models.base import TflModel


class Crowding(TflModel):
    type: str = pydantic.Field(alias="$type")
