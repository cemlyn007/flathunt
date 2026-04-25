import pydantic

from tfl.models.json.common.base import TflModel
from tfl.models.json.journey.disambiguation_option import DisambiguationOption


class Disambiguation(TflModel):
    type: str = pydantic.Field(alias="$type")
    disambiguation_options: list[DisambiguationOption] | None = None
    match_status: str
