"""Pydantic models for TfL StopPoint API responses."""

from typing import Literal, Optional

import pydantic

from tfl.models.base import TflModel


class AdditionalProperties(TflModel):
    """Additional properties for a stop point, such as facilities and contact info."""

    type: str = pydantic.Field(alias="$type")
    category: str
    key: str
    source_system_key: str
    value: str


class LineGroup(TflModel):
    """Line group information for a stop point."""

    type: Optional[str] = pydantic.Field(default=None, alias="$type")
    naptan_id_reference: Optional[str] = None
    station_atco_code: Optional[str] = None
    line_identifier: list[str] = pydantic.Field(default_factory=list)


class LineModeGroup(TflModel):
    """Line mode group information."""

    type: Optional[str] = pydantic.Field(default=None, alias="$type")
    mode_name: str
    line_identifier: list[str] = pydantic.Field(default_factory=list)


class StopPointLine(TflModel):
    """Line information for a stop point."""

    type: Optional[str] = pydantic.Field(default=None, alias="$type")
    line_type: Optional[str] = pydantic.Field(default=None, alias="type")
    route_type: Optional[str] = None
    status: Optional[Literal["Unknown"]] = None
    id: str
    name: str
    uri: str
    full_name: Optional[str] = None
    mode_name: Optional[str] = None
    disruptions: list = pydantic.Field(default_factory=list)
    created: Optional[str] = None
    modified: Optional[str] = None
    line_statuses: list = pydantic.Field(default_factory=list)
    route_sections: list = pydantic.Field(default_factory=list)
    service_types: list = pydantic.Field(default_factory=list)
    crowding: Optional[dict] = None


class StopPointDetail(TflModel):
    """Detailed stop point model for TfL API responses.

    This represents a stop point such as a tube station entrance, bus stop,
    or other transport stop.
    """

    type: str = pydantic.Field(alias="$type")
    naptan_id: str
    indicator: Optional[str] = None
    stop_letter: Optional[str] = None
    modes: list[str] = pydantic.Field(default_factory=list)
    ics_code: Optional[str] = None
    stop_type: Optional[str] = None
    station_naptan: Optional[str] = None
    hub_naptan_code: Optional[str] = None
    lines: list[StopPointLine] = pydantic.Field(default_factory=list)
    line_group: list[LineGroup] = pydantic.Field(default_factory=list)
    line_mode_groups: list[LineModeGroup] = pydantic.Field(default_factory=list)
    status: bool = True
    id: str
    common_name: str
    place_type: str
    additional_properties: list[AdditionalProperties] = pydantic.Field(
        default_factory=list
    )
    lat: Optional[float] = None
    lon: Optional[float] = None
    children: list["StopPointDetail"] = pydantic.Field(default_factory=list)
    children_urls: list[str] = pydantic.Field(default_factory=list)
    url: Optional[str] = None
    distance: Optional[float] = None

    def get_property(self, key: str) -> Optional[str]:
        """Get a specific additional property value by key.

        Args:
            key: The key name of the property to retrieve.

        Returns:
            The property value if found, None otherwise.
        """
        for prop in self.additional_properties:
            if prop.key == key:
                return prop.value
        return None

    def get_properties_by_category(self, category: str) -> list[AdditionalProperties]:
        """Get all additional properties for a specific category.

        Args:
            category: The category name (e.g., "Facility", "Address").

        Returns:
            List of AdditionalProperties matching the category.
        """
        return [
            prop for prop in self.additional_properties if prop.category == category
        ]


class StopPointSearchMatch(TflModel):
    """A single match from a stop point search."""

    type: str = pydantic.Field(alias="$type")
    ics_id: Optional[str] = None
    modes: list[str] = pydantic.Field(default_factory=list)
    zone: Optional[str] = None
    id: str
    name: str
    lat: float
    lon: float
    url: Optional[str] = None
    top_most_parent_id: Optional[str] = None


class StopPointSearchResponse(TflModel):
    """Response from a stop point search query."""

    type: str = pydantic.Field(alias="$type")
    query: str
    total: int
    matches: list[StopPointSearchMatch] = pydantic.Field(default_factory=list)


class StopPointsResponse(TflModel):
    """Response containing a list of stop points."""

    type: str = pydantic.Field(alias="$type")
    stop_points: list[StopPointDetail] = pydantic.Field(default_factory=list)
    page_size: Optional[int] = None
    total: Optional[int] = None
    page: Optional[int] = None


# Type adapter for parsing an array of StopPointDetail directly
# Use this to parse the response from /StopPoint/Mode/{mode}
StopPointList = pydantic.TypeAdapter(list[StopPointDetail])
