import copy
import enum
import json
import logging
from collections.abc import Sequence
from typing import Any, Literal, Optional

import httpx
import polyline as _polyline
import pydantic
from tenacity import AsyncRetrying

from rightmove import models
from rightmove.property_details import parse_property_details

logger = logging.getLogger(__name__)

__all__ = [
    "SEARCH_LIST_MAX_RESULTS",
    "SEARCH_MAP_MAX_RESULTS",
    "HTTPError",
    "SortType",
    "MustHave",
    "DontShow",
    "FurnishType",
    "PropertyType",
    "SearchQuery",
    "Rightmove",
    "polyline_identifier",
    "property_url",
]


SEARCH_LIST_MAX_RESULTS = 1000
"The maximum number of results the listing search API will return indices up to."

SEARCH_MAP_MAX_RESULTS = 499
"The maximum number of results the map search API will return up to."


class HTTPError(Exception): ...


class SortType(enum.IntEnum):
    """Sort type for search results."""

    LOWEST_PRICE = 1
    HIGHEST_PRICE = 2
    NEAREST_FIRST = 4
    MOST_RECENT = 6
    OLDEST_LISTED = 10


class MustHave(enum.Enum):
    """Must have property features."""

    GARDEN = "garden"
    PARKING = "parking"


class DontShow(enum.Enum):
    """Property types to exclude from search results."""

    HOUSE_SHARE = "houseShare"
    RETIREMENT = "retirement"
    STUDENT = "student"


class FurnishType(enum.Enum):
    """Furnish type for properties."""

    FURNISHED = "furnished"
    PART_FURNISHED = "partFurnished"
    UNFURNISHED = "unfurnished"


class PropertyType(enum.Enum):
    """Property types for search results."""

    FLAT = "flat"
    LAND = "land"
    PARK_HOME = "park-home"
    PRIVATE_HALLS = "private-halls"
    DETACHED = "detached"
    SEMI_DETACHED = "semi-detached"
    TERRACED = "terraced"


class SearchQuery(pydantic.BaseModel):
    location_identifier: str
    min_bedrooms: int = 1
    max_bedrooms: int = 10
    min_price: int = 0
    max_price: Optional[int] = None
    min_bathrooms: int = 1
    max_bathrooms: int = 5
    number_of_properties_per_page: int = pydantic.Field(gt=0, le=95, default=95)
    radius: float = pydantic.Field(gt=-1, default=0)
    "In Miles. Set to 0 to only return properties in area."
    sort_type: SortType = SortType.NEAREST_FIRST
    must_have: Sequence[MustHave] = ()
    dont_show: Sequence[DontShow] = pydantic.Field(
        default=(
            DontShow.HOUSE_SHARE,
            DontShow.RETIREMENT,
            DontShow.STUDENT,
        )
    )
    furnish_types: Sequence[FurnishType] = pydantic.Field(
        default=(
            FurnishType.FURNISHED,
            FurnishType.PART_FURNISHED,
            FurnishType.UNFURNISHED,
        )
    )
    property_types: Sequence[PropertyType] = pydantic.Field(
        default=(
            PropertyType.FLAT,
            PropertyType.DETACHED,
            PropertyType.SEMI_DETACHED,
            PropertyType.TERRACED,
        )
    )
    is_fetching: bool
    max_days_since_added: Optional[int] = None
    channel: Literal["RENT", "BUY"] = "RENT"
    area_size_unit: Literal["sqm"] = "sqm"
    currency_code: Literal["GBP"] = "GBP"
    include_let_agreed: bool = False


def polyline_identifier(polyline: list[tuple[float, float]]) -> str:
    return "USERDEFINEDAREA^" + json.dumps(
        {"polylines": _polyline.encode(polyline)}, separators=(", ", ":")
    )


class Rightmove:
    def __init__(self, retrying: Optional[AsyncRetrying] = None) -> None:
        self._raw_api = _RawRightmove()
        if retrying is not None:
            self._raw_api.lookup = retrying.wraps(self._raw_api.lookup)  # type: ignore
            self._raw_api.listing_search = retrying.wraps(self._raw_api.listing_search)  # type: ignore
            self._raw_api.map_search = retrying.wraps(self._raw_api.map_search)  # type: ignore

    async def lookup(
        self,
        query: str,
        limit: Optional[int] = None,
    ) -> models.LookupMatches:
        """Get the location IDs related to a search query.

        Args:
            query (str): Search location query.
            limit (int): Limit, defaulting to the API max limit.

        Returns:
            models.LookupMatches: Matches
        """
        lookup_results = await self._raw_api.lookup(query=query, limit=limit)
        return models.LookupMatches.model_validate(lookup_results)

    async def search(
        self,
        query: SearchQuery,
    ) -> list[models.ListingProperty]:
        """Search for properties using the listing search endpoint.

        Args:
            query (SearchQuery): Search configuration parameters

        Returns:
            list[models.ListingProperty]: List of properties matching the search criteria
                of up to a max length of 1000.
        """
        search_results = await self._raw_api.listing_search(query=query)
        return [
            models.ListingProperty.model_validate(property)
            for property in search_results["properties"]
        ]

    async def map_search(
        self,
        query: SearchQuery,
    ) -> tuple[list[models.MapProperty], int]:
        """Search for properties using the map search endpoint.

        Args:
            query (SearchQuery): Search configuration parameters

        Returns:
            list[models.MapProperty]: List of properties matching the search criteria
                of up to a max length of 499.
            int: Total number of properties matching the search criteria.
        """
        location_results = await self._raw_api.map_search(query=query)
        features = location_results["geoJsonProperties"]["features"]
        return [
            models.MapProperty.model_validate(feature["properties"])
            for feature in features
        ], int(location_results["resultCount"].replace(",", ""))

    async def get_property_details(
        self,
        property_url: str,
    ) -> models.PropertyDetails:
        """Fetch and parse the details page for a property.

        Args:
            property_url: The property URL path (e.g. ``MapProperty.property_url``).

        Returns:
            A ``PropertyDetails`` instance parsed from the page.
        """
        html = await self._raw_api.property_details(property_url)
        return parse_property_details(html)


def property_url(property_url: str) -> str:
    return f"https://{_RawRightmove.BASE_HOST}{property_url}"


class _RawRightmove:
    BASE_HOST = "www.rightmove.co.uk"
    LOS_HOST = "los.rightmove.co.uk"
    LOS_LIMIT = 20
    "The maximum search results the lookup service will return."

    _HEADERS = {
        "User-Agent": "IAmLookingToRent/0.0.0",
        "Accept": "*/*",
    }

    async def lookup(self, query: str, limit: Optional[int] = None) -> dict[str, Any]:
        """Get the location IDs related to a search query.

        Args:
            query (str): Search location query.
            limit (int): Limit, defaulting to the API max limit.

        Returns:
            dict[str, Any]: Matches
        """
        async with httpx.AsyncClient(base_url=f"https://{self.LOS_HOST}") as client:
            response = await client.get(
                "/typeahead",
                params={
                    "query": query,
                    "limit": limit or self.LOS_LIMIT,
                    "exclude": "",
                },
                headers=self._HEADERS,
            )
            response.raise_for_status()
            return response.json()

    async def listing_search(
        self,
        query: SearchQuery,
    ) -> dict[str, Any]:
        params = self._get_listing_params(query)
        async with httpx.AsyncClient(base_url=f"https://{self.BASE_HOST}") as client:
            response = await client.get(
                "/api/property-search/listing/search",
                params=params,
                headers=self._HEADERS,
            )
            response.raise_for_status()
            if not response.content or not response.text.strip():
                return {"properties": [], "resultCount": "0"}
            try:
                result = response.json()
            except Exception:
                logger.error(
                    "Failed to decode listing search JSON response. status=%s content_length=%d content=%r",
                    response.status_code,
                    len(response.content),
                    response.content[:500],
                )
                raise

            full_response = copy.deepcopy(result)
            while len(full_response["properties"]) < min(
                int(result["resultCount"].replace(",", "")), SEARCH_LIST_MAX_RESULTS
            ):
                params = copy.deepcopy(params)
                params["index"] = int(result["pagination"]["next"])
                response = await client.get(
                    "/api/property-search/listing/search",
                    params=params,
                    headers=self._HEADERS,
                )
                response.raise_for_status()
                result = response.json()
                full_response["properties"].extend(result["properties"])
            return full_response

    async def property_details(self, property_url: str) -> str:
        async with httpx.AsyncClient(base_url=f"https://{self.BASE_HOST}") as client:
            response = await client.get(property_url, headers=self._HEADERS)
            response.raise_for_status()
            return response.text

    async def map_search(
        self,
        query: SearchQuery,
    ) -> dict[str, Any]:
        params = self._get_map_params(query)
        async with httpx.AsyncClient(base_url=f"https://{self.BASE_HOST}") as client:
            response = await client.get(
                "/api/property-search/map/search",
                params=params,
                headers=self._HEADERS,
            )
            response.raise_for_status()
            if not response.content or not response.text.strip():
                return {"geoJsonProperties": {"features": []}, "resultCount": "0"}
            try:
                result = response.json()
            except Exception:
                logger.error(
                    "Failed to decode map search JSON response. status=%s content_length=%d content=%r",
                    response.status_code,
                    len(response.content),
                    response.content[:500],
                )
                raise
            return result

    def property_url(self, property_url: str) -> str:
        return f"https://{self.BASE_HOST}{property_url}"

    def _get_common_params(self, query: SearchQuery) -> dict[str, Any]:
        params: dict[str, Any] = {
            "locationIdentifier": query.location_identifier,
            "numberOfPropertiesPerPage": query.number_of_properties_per_page,
            "radius": query.radius,
            "sortType": query.sort_type.value,
            "channel": query.channel,
            "transactionType": query.channel,
        }
        if query.dont_show:
            params["dontShow"] = ",".join(d.value for d in query.dont_show)
        if query.must_have:
            params["mustHave"] = ",".join(m.value for m in query.must_have)
        if query.property_types:
            params["propertyTypes"] = ",".join(p.value for p in query.property_types)
        if query.max_days_since_added is not None:
            params["maxDaysSinceAdded"] = query.max_days_since_added
        if query.min_bedrooms:
            params["minBedrooms"] = query.min_bedrooms
        if query.max_bedrooms:
            params["maxBedrooms"] = query.max_bedrooms
        return params

    def _get_listing_params(self, query: SearchQuery) -> dict[str, Any]:
        params = self._get_common_params(query)
        params.update(
            {
                "includeLetAgreed": query.include_let_agreed,
                "areaSizeUnit": query.area_size_unit,
                "currencyCode": query.currency_code,
                "isFetching": query.is_fetching,
            }
        )
        if query.min_price:
            params["minPrice"] = query.min_price
        if query.max_price:
            params["maxPrice"] = query.max_price
        if query.furnish_types:
            params["furnishTypes"] = ",".join(f.value for f in query.furnish_types)
        if query.include_let_agreed:
            params["_includeLetAgreed"] = "on"
        if query.min_bathrooms:
            params["minBathrooms"] = query.min_bathrooms
        if query.max_bathrooms:
            params["maxBathrooms"] = query.max_bathrooms
        return params

    def _get_map_params(self, query: SearchQuery) -> dict[str, Any]:
        return self._get_common_params(query)
