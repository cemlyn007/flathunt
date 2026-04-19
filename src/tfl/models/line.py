"""Pydantic models for TfL Line API responses."""

import pydantic

from tfl.models.base import TflModel
from tfl.models.journey_results import ModeId


class LineDisruption(TflModel):
    """Disruption information for a line."""

    type: str = pydantic.Field(alias="$type")
    category: str | None = None
    category_description: str | None = None
    description: str | None = None
    affected_routes: list = pydantic.Field(default_factory=list)
    affected_stops: list = pydantic.Field(default_factory=list)
    closure_text: str | None = None


class LineCrowding(TflModel):
    """Crowding information for a line."""

    type: str = pydantic.Field(alias="$type")


class LineServiceType(TflModel):
    """Service type information for a line (e.g., Regular, Night).

    Note: The TFL API returns this as LineServiceTypeInfo in some endpoints.
    """

    type: str = pydantic.Field(alias="$type")
    name: str
    uri: str | None = None


class MatchedRoute(TflModel):
    """Matched route information returned by the /Line/Route endpoint.

    This represents a route section with direction and terminus information.
    """

    type: str | None = pydantic.Field(default=None, alias="$type")
    name: str | None = None
    direction: str | None = None
    origination_name: str | None = None
    destination_name: str | None = None
    originator: str | None = None
    destination: str | None = None
    service_type: str | None = None
    valid_to: str | None = None
    valid_from: str | None = None


class LineRouteSection(TflModel):
    """Route section information for a line."""

    type: str | None = pydantic.Field(default=None, alias="$type")
    name: str | None = None
    direction: str | None = None
    origination_name: str | None = None
    destination_name: str | None = None
    originator: str | None = None
    destination: str | None = None
    service_type: str | None = None
    valid_to: str | None = None
    valid_from: str | None = None


class LineStatusDisruption(TflModel):
    """Disruption details within a line status."""

    type: str = pydantic.Field(alias="$type")
    category: str | None = None
    category_description: str | None = None
    description: str | None = None
    additional_info: str | None = None
    created: str | None = None
    last_update: str | None = None


class LineStatusValidityPeriod(TflModel):
    """Validity period for a line status."""

    type: str = pydantic.Field(alias="$type")
    from_date: str
    to_date: str
    is_now: bool = False


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


class Line(TflModel):
    """A TfL line (e.g., a tube line like Bakerloo, Central, etc.)."""

    type: str = pydantic.Field(alias="$type")
    id: str
    name: str
    mode_name: ModeId
    disruptions: list[LineDisruption] = pydantic.Field(default_factory=list)
    created: str
    modified: str
    line_statuses: list[LineStatus] = pydantic.Field(default_factory=list)
    route_sections: list[MatchedRoute | LineRouteSection] = pydantic.Field(
        default_factory=list
    )
    service_types: list[LineServiceType] = pydantic.Field(default_factory=list)
    crowding: LineCrowding | None = None


# Type adapter for parsing an array of Line directly
LineList = pydantic.TypeAdapter(list[Line])

# Type adapter for parsing the /Line/Route endpoint response
LinesRoutesResponse = pydantic.TypeAdapter(list[Line])
