"""Pydantic models for TfL Line API responses."""

from typing import Optional

import pydantic

from tfl.models.base import TflModel
from tfl.models.journey_results import ModeId


class LineDisruption(TflModel):
    """Disruption information for a line."""

    type: str = pydantic.Field(alias="$type")
    category: Optional[str] = None
    category_description: Optional[str] = None
    description: Optional[str] = None
    affected_routes: list = pydantic.Field(default_factory=list)
    affected_stops: list = pydantic.Field(default_factory=list)
    closure_text: Optional[str] = None


class LineCrowding(TflModel):
    """Crowding information for a line."""

    type: str = pydantic.Field(alias="$type")


class LineServiceType(TflModel):
    """Service type information for a line (e.g., Regular, Night).

    Note: The TFL API returns this as LineServiceTypeInfo in some endpoints.
    """

    type: str = pydantic.Field(alias="$type")
    name: str
    uri: Optional[str] = None


class MatchedRoute(TflModel):
    """Matched route information returned by the /Line/Route endpoint.

    This represents a route section with direction and terminus information.
    """

    type: Optional[str] = pydantic.Field(default=None, alias="$type")
    name: Optional[str] = None
    direction: Optional[str] = None
    origination_name: Optional[str] = None
    destination_name: Optional[str] = None
    originator: Optional[str] = None
    destination: Optional[str] = None
    service_type: Optional[str] = None
    valid_to: Optional[str] = None
    valid_from: Optional[str] = None


class LineRouteSection(TflModel):
    """Route section information for a line."""

    type: Optional[str] = pydantic.Field(default=None, alias="$type")
    name: Optional[str] = None
    direction: Optional[str] = None
    origination_name: Optional[str] = None
    destination_name: Optional[str] = None
    originator: Optional[str] = None
    destination: Optional[str] = None
    service_type: Optional[str] = None
    valid_to: Optional[str] = None
    valid_from: Optional[str] = None


class LineStatusDisruption(TflModel):
    """Disruption details within a line status."""

    type: str = pydantic.Field(alias="$type")
    category: Optional[str] = None
    category_description: Optional[str] = None
    description: Optional[str] = None
    additional_info: Optional[str] = None
    created: Optional[str] = None
    last_update: Optional[str] = None


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
    reason: Optional[str] = None
    created: Optional[str] = None
    modified: Optional[str] = None
    validity_periods: list[LineStatusValidityPeriod] = pydantic.Field(
        default_factory=list
    )
    disruption: Optional[LineStatusDisruption] = None


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
    crowding: Optional[LineCrowding] = None


# Type adapter for parsing an array of Line directly
LineList = pydantic.TypeAdapter(list[Line])

# Type adapter for parsing the /Line/Route endpoint response
LinesRoutesResponse = pydantic.TypeAdapter(list[Line])
