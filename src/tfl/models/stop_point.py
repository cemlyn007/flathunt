"""Pydantic models for TfL StopPoint API responses."""

from typing import Optional

import pydantic


class AdditionalProperties(pydantic.BaseModel):
    """Additional properties for a stop point, such as facilities and contact info."""

    model_config = pydantic.ConfigDict(populate_by_name=True)

    type: str = pydantic.Field(alias="$type")
    category: str
    key: str
    source_system_key: str = pydantic.Field(alias="sourceSystemKey")
    value: str


class LineGroup(pydantic.BaseModel):
    """Line group information for a stop point."""

    model_config = pydantic.ConfigDict(populate_by_name=True)

    type: Optional[str] = pydantic.Field(default=None, alias="$type")
    naptan_id_reference: Optional[str] = pydantic.Field(
        default=None, alias="naptanIdReference"
    )
    station_atco_code: Optional[str] = pydantic.Field(
        default=None, alias="stationAtcoCode"
    )
    line_identifier: list[str] = pydantic.Field(default=[], alias="lineIdentifier")


class LineModeGroup(pydantic.BaseModel):
    """Line mode group information."""

    model_config = pydantic.ConfigDict(populate_by_name=True)

    type: Optional[str] = pydantic.Field(default=None, alias="$type")
    mode_name: str = pydantic.Field(alias="modeName")
    line_identifier: list[str] = pydantic.Field(default=[], alias="lineIdentifier")


class StopPointLine(pydantic.BaseModel):
    """Line information for a stop point."""

    model_config = pydantic.ConfigDict(populate_by_name=True)

    type: Optional[str] = pydantic.Field(default=None, alias="$type")
    id: str
    name: str
    uri: str
    full_name: Optional[str] = pydantic.Field(default=None, alias="fullName")
    mode_name: Optional[str] = pydantic.Field(default=None, alias="modeName")
    disruptions: list = pydantic.Field(default=[])
    created: Optional[str] = None
    modified: Optional[str] = None
    line_statuses: list = pydantic.Field(default=[], alias="lineStatuses")
    route_sections: list = pydantic.Field(default=[], alias="routeSections")
    service_types: list = pydantic.Field(default=[], alias="serviceTypes")
    crowding: Optional[dict] = None


class StopPointDetail(pydantic.BaseModel):
    """Detailed stop point model for TfL API responses.

    This represents a stop point such as a tube station entrance, bus stop,
    or other transport stop.
    """

    model_config = pydantic.ConfigDict(populate_by_name=True)

    type: str = pydantic.Field(alias="$type")
    naptan_id: str = pydantic.Field(alias="naptanId")
    indicator: Optional[str] = None
    stop_letter: Optional[str] = pydantic.Field(default=None, alias="stopLetter")
    modes: list[str] = pydantic.Field(default=[])
    ics_code: Optional[str] = pydantic.Field(default=None, alias="icsCode")
    stop_type: Optional[str] = pydantic.Field(default=None, alias="stopType")
    station_naptan: Optional[str] = pydantic.Field(default=None, alias="stationNaptan")
    hub_naptan_code: Optional[str] = pydantic.Field(default=None, alias="hubNaptanCode")
    lines: list[StopPointLine] = pydantic.Field(default=[])
    line_group: list[LineGroup] = pydantic.Field(default=[], alias="lineGroup")
    line_mode_groups: list[LineModeGroup] = pydantic.Field(
        default=[], alias="lineModeGroups"
    )
    status: bool = True
    id: str
    common_name: str = pydantic.Field(alias="commonName")
    place_type: str = pydantic.Field(alias="placeType")
    additional_properties: list[AdditionalProperties] = pydantic.Field(
        default=[], alias="additionalProperties"
    )
    lat: Optional[float] = None
    lon: Optional[float] = None
    children: list["StopPointDetail"] = pydantic.Field(default=[])
    children_urls: list[str] = pydantic.Field(default=[], alias="childrenUrls")
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


class StopPointSearchMatch(pydantic.BaseModel):
    """A single match from a stop point search."""

    model_config = pydantic.ConfigDict(populate_by_name=True)

    type: str = pydantic.Field(alias="$type")
    ics_id: Optional[str] = pydantic.Field(default=None, alias="icsId")
    modes: list[str] = pydantic.Field(default=[])
    zone: Optional[str] = None
    id: str
    name: str
    lat: float
    lon: float
    url: Optional[str] = None
    top_most_parent_id: Optional[str] = pydantic.Field(
        default=None, alias="topMostParentId"
    )


class StopPointSearchResponse(pydantic.BaseModel):
    """Response from a stop point search query."""

    model_config = pydantic.ConfigDict(populate_by_name=True)

    type: str = pydantic.Field(alias="$type")
    query: str
    total: int
    matches: list[StopPointSearchMatch] = pydantic.Field(default=[])


class StopPointsResponse(pydantic.BaseModel):
    """Response containing a list of stop points."""

    model_config = pydantic.ConfigDict(populate_by_name=True)

    type: str = pydantic.Field(alias="$type")
    stop_points: list[StopPointDetail] = pydantic.Field(default=[], alias="stopPoints")
    page_size: Optional[int] = pydantic.Field(default=None, alias="pageSize")
    total: Optional[int] = None
    page: Optional[int] = None


# Type adapter for parsing an array of StopPointDetail directly
# Use this to parse the response from /StopPoint/Mode/{mode}
StopPointList = pydantic.TypeAdapter(list[StopPointDetail])
