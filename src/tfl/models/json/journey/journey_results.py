import pydantic

from tfl.models.json.common.base import TflModel
from tfl.models.json.journey.journey import Journey
from tfl.models.json.journey.journey_vector import JourneyVector
from tfl.models.json.journey.search_criteria import SearchCriteria
from tfl.models.json.line.line_journey import Line


class JourneyResults(TflModel):
    type: str = pydantic.Field(alias="$type")
    journeys: list[Journey]
    lines: list[Line]
    stop_messages: list
    recommended_max_age_minutes: int
    search_criteria: SearchCriteria
    journey_vector: JourneyVector
