"""Validity period for a line status."""

import pydantic

from tfl.models.json.common.base import TflModel


class LineStatusValidityPeriod(TflModel):
    """Validity period for a line status."""

    type: str = pydantic.Field(alias="$type")
    from_date: str
    to_date: str
    is_now: bool = False
