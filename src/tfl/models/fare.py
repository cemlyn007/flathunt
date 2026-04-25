import pydantic

from tfl.models.base import TflModel


class Fare(TflModel):
    type: str = pydantic.Field(alias="$type")
    total_cost: int
    fares: list
    caveats: list
