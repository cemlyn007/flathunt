import pydantic

from tfl.models.base import TflModel
from tfl.models.place import Place


class DisambiguationOption(TflModel):
    type: str = pydantic.Field(alias="$type")
    parameter_value: str
    uri: str
    place: Place
    match_quality: int
