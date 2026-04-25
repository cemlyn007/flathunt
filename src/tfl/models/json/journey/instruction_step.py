import pydantic

from tfl.models.json.common.base import TflModel
from tfl.models.json.journey.path_attribute import PathAttribute


class InstructionStep(TflModel):
    type: str = pydantic.Field(alias="$type")
    description: str
    turn_direction: str
    street_name: str
    distance: int
    cumulative_distance: int
    sky_direction: int
    sky_direction_description: str
    cumulative_travel_time: int
    latitude: float
    longitude: float
    path_attribute: PathAttribute
    description_heading: str
    track_type: str
    travel_time: int
