import pydantic

from tfl.models.json.common.base import TflModel


class JourneyVector(TflModel):
    type: str = pydantic.Field(alias="$type")
    from_location: str = pydantic.Field(alias="from")
    to_location: str = pydantic.Field(alias="to")
    via: str
    uri: str
