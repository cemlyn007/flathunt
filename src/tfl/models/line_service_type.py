"""Service type information for a TfL line."""

import pydantic

from tfl.models.base import TflModel


class LineServiceType(TflModel):
    """Service type information for a line (e.g., Regular, Night).

    Note: The TFL API returns this as LineServiceTypeInfo in some endpoints.
    """

    type: str = pydantic.Field(alias="$type")
    name: str
    uri: str | None = None
