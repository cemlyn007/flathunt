"""Pydantic model for additional properties of a stop point."""

import pydantic

from tfl.models.json.common.base import TflModel


class AdditionalProperties(TflModel):
    """Additional properties for a stop point, such as facilities and contact info."""

    type: str = pydantic.Field(alias="$type")
    category: str
    key: str
    source_system_key: str
    value: str
