"""Pydantic models for detailed stop point information."""

import pydantic

from tfl.models.additional_properties import AdditionalProperties
from tfl.models.base import TflModel
from tfl.models.line_group import LineGroup
from tfl.models.line_mode_group import LineModeGroup
from tfl.models.stop_point_line import StopPointLine


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


# Type adapter for parsing an array of StopPointDetail directly
# Use this to parse the response from /StopPoint/Mode/{mode}
StopPointList = pydantic.TypeAdapter(list[StopPointDetail])
