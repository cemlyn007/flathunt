import pydantic

from tfl.models.json.common.base import TflModel


class Place(TflModel):
    type: str = pydantic.Field(alias="$type")
    url: str
    common_name: str
    place_type: str
    additional_properties: list
    lat: float
    lon: float
