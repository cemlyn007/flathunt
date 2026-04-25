import pydantic

from tfl.models.json.common.base import TflModel
from tfl.models.json.stop_point.place import Place


class DisambiguationOption(TflModel):
    type: str = pydantic.Field(alias="$type")
    parameter_value: str
    uri: str
    place: Place
    match_quality: int
