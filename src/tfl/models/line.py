"""Pydantic models for TfL Line API responses."""

from typing import Optional

import pydantic

from tfl.models.journey_results import ModeId


class LineDisruption(pydantic.BaseModel):
    """Disruption information for a line."""

    model_config = pydantic.ConfigDict(populate_by_name=True)

    type: str = pydantic.Field(alias="$type")
    category: Optional[str] = None
    category_description: Optional[str] = pydantic.Field(
        default=None, alias="categoryDescription"
    )
    description: Optional[str] = None
    affected_routes: list = pydantic.Field(default=[], alias="affectedRoutes")
    affected_stops: list = pydantic.Field(default=[], alias="affectedStops")
    closure_text: Optional[str] = pydantic.Field(default=None, alias="closureText")


class LineCrowding(pydantic.BaseModel):
    """Crowding information for a line."""

    model_config = pydantic.ConfigDict(populate_by_name=True)

    type: str = pydantic.Field(alias="$type")


class LineServiceType(pydantic.BaseModel):
    """Service type information for a line (e.g., Regular, Night).

    Note: The TFL API returns this as LineServiceTypeInfo in some endpoints.
    """

    model_config = pydantic.ConfigDict(populate_by_name=True)

    type: str = pydantic.Field(alias="$type")
    name: str
    uri: Optional[str] = None


class MatchedRoute(pydantic.BaseModel):
    """Matched route information returned by the /Line/Route endpoint.

    This represents a route section with direction and terminus information.
    """

    model_config = pydantic.ConfigDict(populate_by_name=True)

    type: Optional[str] = pydantic.Field(default=None, alias="$type")
    name: Optional[str] = None
    direction: Optional[str] = None
    origination_name: Optional[str] = pydantic.Field(
        default=None, alias="originationName"
    )
    destination_name: Optional[str] = pydantic.Field(
        default=None, alias="destinationName"
    )
    originator: Optional[str] = None
    destination: Optional[str] = None
    service_type: Optional[str] = pydantic.Field(default=None, alias="serviceType")
    valid_to: Optional[str] = pydantic.Field(default=None, alias="validTo")
    valid_from: Optional[str] = pydantic.Field(default=None, alias="validFrom")


class LineRouteSection(pydantic.BaseModel):
    """Route section information for a line."""

    model_config = pydantic.ConfigDict(populate_by_name=True)

    type: Optional[str] = pydantic.Field(default=None, alias="$type")
    name: Optional[str] = None
    direction: Optional[str] = None
    origination_name: Optional[str] = pydantic.Field(
        default=None, alias="originationName"
    )
    destination_name: Optional[str] = pydantic.Field(
        default=None, alias="destinationName"
    )
    originator: Optional[str] = None
    destination: Optional[str] = None
    service_type: Optional[str] = pydantic.Field(default=None, alias="serviceType")
    valid_to: Optional[str] = pydantic.Field(default=None, alias="validTo")
    valid_from: Optional[str] = pydantic.Field(default=None, alias="validFrom")


class LineStatusDisruption(pydantic.BaseModel):
    """Disruption details within a line status."""

    model_config = pydantic.ConfigDict(populate_by_name=True)

    type: str = pydantic.Field(alias="$type")
    category: Optional[str] = None
    category_description: Optional[str] = pydantic.Field(
        default=None, alias="categoryDescription"
    )
    description: Optional[str] = None
    additional_info: Optional[str] = pydantic.Field(
        default=None, alias="additionalInfo"
    )
    created: Optional[str] = None
    last_update: Optional[str] = pydantic.Field(default=None, alias="lastUpdate")


class LineStatusValidityPeriod(pydantic.BaseModel):
    """Validity period for a line status."""

    model_config = pydantic.ConfigDict(populate_by_name=True)

    type: str = pydantic.Field(alias="$type")
    from_date: str = pydantic.Field(alias="fromDate")
    to_date: str = pydantic.Field(alias="toDate")
    is_now: bool = pydantic.Field(default=False, alias="isNow")


class LineStatus(pydantic.BaseModel):
    """Status information for a line."""

    model_config = pydantic.ConfigDict(populate_by_name=True)

    type: str = pydantic.Field(alias="$type")
    id: int
    status_severity: int = pydantic.Field(alias="statusSeverity")
    status_severity_description: str = pydantic.Field(alias="statusSeverityDescription")
    reason: Optional[str] = None
    created: Optional[str] = None
    modified: Optional[str] = None
    validity_periods: list[LineStatusValidityPeriod] = pydantic.Field(
        default=[], alias="validityPeriods"
    )
    disruption: Optional[LineStatusDisruption] = None


class Line(pydantic.BaseModel):
    """A TfL line (e.g., a tube line like Bakerloo, Central, etc.)."""

    model_config = pydantic.ConfigDict(populate_by_name=True)

    type: str = pydantic.Field(alias="$type")
    id: str
    name: str
    mode_name: ModeId = pydantic.Field(alias="modeName")
    disruptions: list[LineDisruption] = pydantic.Field(default=[])
    created: str
    modified: str
    line_statuses: list[LineStatus] = pydantic.Field(default=[], alias="lineStatuses")
    route_sections: list[MatchedRoute | LineRouteSection] = pydantic.Field(
        default=[], alias="routeSections"
    )
    service_types: list[LineServiceType] = pydantic.Field(
        default=[], alias="serviceTypes"
    )
    crowding: Optional[LineCrowding] = None


# Type adapter for parsing an array of Line directly
LineList = pydantic.TypeAdapter(list[Line])

# Type adapter for parsing the /Line/Route endpoint response
LinesRoutesResponse = pydantic.TypeAdapter(list[Line])
