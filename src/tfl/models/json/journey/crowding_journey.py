import pydantic

from tfl.models.json.common.base import TflModel


class Crowding(TflModel):
    type: str = pydantic.Field(alias="$type")
