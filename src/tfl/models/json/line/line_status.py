"""Status information for a TfL line."""

import pydantic

from tfl.models.json.common.base import TflModel
from tfl.models.json.line.line_status_disruption import LineStatusDisruption
from tfl.models.json.line.line_status_validity_period import LineStatusValidityPeriod


class LineStatus(TflModel):
    """Status information for a line."""

    type: str = pydantic.Field(alias="$type")
    id: int
    status_severity: int
    status_severity_description: str
    reason: str | None = None
    created: str | None = None
    modified: str | None = None
    validity_periods: list[LineStatusValidityPeriod] = pydantic.Field(
        default_factory=list
    )
    disruption: LineStatusDisruption | None = None
