import pydantic

from tfl.models.json.common.base import TflModel
from tfl.models.json.common.mode_id import ModeId


class Mode(TflModel):
    type: str = pydantic.Field(alias="$type")
    id: ModeId
    name: str
    mode_type: str = pydantic.Field(alias="type")
    route_type: str
    status: str
    mot_type: str
    network: str
