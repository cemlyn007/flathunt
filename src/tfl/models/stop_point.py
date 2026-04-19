"""Pydantic models for TfL StopPoint API responses."""

from typing import Literal

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

    type: str | None = pydantic.Field(default=None, alias="$type")
    naptan_id_reference: str | None = None
    station_atco_code: str | None = None
    line_identifier: list[str] = pydantic.Field(default_factory=list)


class LineModeGroup(TflModel):
    """Line mode group information."""

    type: str | None = pydantic.Field(default=None, alias="$type")
    mode_name: str
    line_identifier: list[str] = pydantic.Field(default_factory=list)


class StopPointLine(TflModel):
    """Line information for a stop point."""

    type: str | None = pydantic.Field(default=None, alias="$type")
    line_type: str | None = pydantic.Field(default=None, alias="type")
    route_type: str | None = None
    status: Literal["Unknown"] | None = None
    id: str
    name: str
    uri: str
    full_name: str | None = None
    mode_name: str | None = None
    disruptions: list = pydantic.Field(default_factory=list)
    created: str | None = None
    modified: str | None = None
    line_statuses: list = pydantic.Field(default_factory=list)
    route_sections: list = pydantic.Field(default_factory=list)
    service_types: list = pydantic.Field(default_factory=list)
    crowding: dict | None = None


class StopPointDetail(TflModel):
    """Detailed stop point model for TfL API responses.

    This represents a stop point such as a tube station entrance, bus stop,
    or other transport stop.
    """

    type: str = pydantic.Field(alias="$type")
    naptan_id: str
    indicator: str | None = None
    stop_letter: str | None = None
    modes: list[str] = pydantic.Field(default_factory=list)
    ics_code: str | None = None
    stop_type: str | None = None
    station_naptan: str | None = None
    hub_naptan_code: str | None = None
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
    lat: float | None = None
    lon: float | None = None
    children: list["StopPointDetail"] = pydantic.Field(default_factory=list)
    children_urls: list[str] = pydantic.Field(default_factory=list)
    url: str | None = None
    distance: float | None = None

    def get_property(self, key: str) -> str | None:
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
    ics_id: str | None = None
    modes: list[str] = pydantic.Field(default_factory=list)
    zone: str | None = None
    id: str
    name: str
    lat: float
    lon: float
    url: str | None = None
    top_most_parent_id: str | None = None


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
    page_size: int | None = None
    total: int | None = None
    page: int | None = None


# Type adapter for parsing an array of StopPointDetail directly
# Use this to parse the response from /StopPoint/Mode/{mode}
StopPointList = pydantic.TypeAdapter(list[StopPointDetail])
