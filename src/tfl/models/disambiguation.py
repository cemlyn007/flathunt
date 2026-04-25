import pydantic

from tfl.models.base import TflModel
from tfl.models.disambiguation_option import DisambiguationOption


class Disambiguation(TflModel):
    type: str = pydantic.Field(alias="$type")
    disambiguation_options: list[DisambiguationOption] | None = None
    match_status: str
