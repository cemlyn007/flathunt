import pydantic

from tfl.models.base import TflModel


class Obstacle(TflModel):
    type: str = pydantic.Field(alias="$type")
    obstacle_type: str = pydantic.Field(alias="type")
    incline: str
    stop_id: int
    position: str
