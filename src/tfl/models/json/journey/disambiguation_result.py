import pydantic

from tfl.models.json.common.base import TflModel
from tfl.models.json.journey.disambiguation import Disambiguation
from tfl.models.json.journey.journey_vector import JourneyVector
from tfl.models.json.journey.search_criteria import SearchCriteria


class DisambiguationResult(TflModel):
    type: str = pydantic.Field(alias="$type")
    to_location_disambiguation: Disambiguation
    from_location_disambiguation: Disambiguation
    via_location_disambiguation: Disambiguation
    recommended_max_age_minutes: int
    search_criteria: SearchCriteria
    journey_vector: JourneyVector
