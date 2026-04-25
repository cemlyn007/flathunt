import pydantic

from tfl.models.json.common.base import TflModel


class LineServiceTypeInfo(TflModel):
    type: str = pydantic.Field(alias="$type")
    name: str
    uri: str
