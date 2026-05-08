import pydantic

from tfl.models.json.common.base import TflModel


class StopPoint(TflModel):
    type: str = pydantic.Field(alias="$type")
    name: str | None = None
    ics_code: str | None = None
    top_most_parent_id: str | None = None
    modes: list[str] | None = None
    stop_letter: str | None = None
    common_name: str
    platform_name: str | None = None
    place_type: str | None = None
    additional_properties: list = pydantic.Field(default_factory=list)
    lat: float | None = None
    lon: float | None = None
    naptan_id: str | None = None
    individual_stop_id: str | None = None
