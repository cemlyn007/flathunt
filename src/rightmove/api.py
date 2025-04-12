from collections.abc import Sequence
import enum
import gzip
import http
import http.client
import json
from typing import Any, Literal, Optional
import copy
import urllib.parse
from rightmove import models
import pydantic


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
    max_price: int
    min_bathrooms: int = 1
    max_bathrooms: int = 5
    number_of_properties_per_page: int = pydantic.Field(gt=0, le=25)
    radius: float = pydantic.Field(gt=0, le=25)
    "In Miles."
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
    view_type: Literal["LIST"] = "LIST"
    area_size_unit: Literal["sqm"] = "sqm"
    currency_code: Literal["GBP"] = "GBP"
    include_let_agreed: bool = False


class Rightmove:
    def __init__(self) -> None:
        self._raw_api = _RawRightmove()

    def lookup(
        self,
        query: str,
    ) -> models.LookupMatches:
        """Get the location IDs related to a search query.

        Args:
            query (str): Search location query.

        Returns:
            models.LookupMatches: Matches
        """
        lookup_results = self._raw_api.lookup(query=query)
        return models.LookupMatches.model_validate(lookup_results)

    def search(
        self,
        query: SearchQuery,
    ) -> list[models.Property]:
        """Search for properties using the provided configuration.

        Args:
            query (SearchQuery): Search configuration parameters

        Returns:
            list[models.Property]: List of properties matching the search criteria
        """
        search_results = self._raw_api.search(query=query)
        return [
            models.Property.model_validate(property)
            for property in search_results["properties"]
        ]

    def property_url(self, property_url: str) -> str:
        return f"https://{self._raw_api.BASE_HOST}{property_url}"


class _RawRightmove:
    BASE_HOST = "www.rightmove.co.uk"
    LOS_HOST = "los.rightmove.co.uk"
    LOS_LIMIT = 20

    # The maximum number of results the API
    # will return indices up to.
    SEARCH_MAX_RESULTS = 1000

    def lookup(
        self,
        query: str,
    ) -> dict[str, Any]:
        """Get the location IDs related to a search query.

        Args:
            query (str): Search location query.

        Returns:
            dict[str, Any]: Matches
        """
        connection = http.client.HTTPSConnection(self.LOS_HOST, port=443)
        try:
            return self._request(
                connection,
                "GET",
                "/typeahead",
                {
                    "query": query,
                    "limit": self.LOS_LIMIT,
                    "exclude": "",
                },
            )
        finally:
            connection.close()

    def search(
        self,
        query: SearchQuery,
    ) -> dict[str, Any]:
        params = self._get_params(query)
        return self._search(params)

    def property_url(self, property_url: str) -> str:
        return f"https://{self.BASE_HOST}{property_url}"

    def _get_params(self, query: SearchQuery) -> dict[str, Any]:
        params = {
            "locationIdentifier": query.location_identifier,
            "minPrice": query.min_price,
            "maxPrice": query.max_price,
            "numberOfPropertiesPerPage": query.number_of_properties_per_page,
            "radius": query.radius,
            "sortType": query.sort_type.value,
            "includeLetAgreed": query.include_let_agreed,
            "viewType": query.view_type,
            "channel": query.channel,
            "areaSizeUnit": query.area_size_unit,
            "currencyCode": query.currency_code,
            "isFetching": query.is_fetching,
        }
        if query.dont_show:
            params["dontShow"] = ",".join(
                dont_show.value for dont_show in query.dont_show
            )
        if query.furnish_types:
            params["furnishTypes"] = ",".join(
                furnish_type.value for furnish_type in query.furnish_types
            )
        if query.must_have:
            params["mustHave"] = ",".join(
                must_have.value for must_have in query.must_have
            )
        if query.property_types:
            params["propertyTypes"] = ",".join(
                property_type.value for property_type in query.property_types
            )
        if query.include_let_agreed:
            params["_includeLetAgreed"] = "on"
        if query.max_days_since_added is not None:
            params["maxDaysSinceAdded"] = query.max_days_since_added
        if query.min_bedrooms:
            params["minBedrooms"] = query.min_bedrooms
        if query.max_bedrooms:
            params["maxBedrooms"] = query.max_bedrooms
        if query.min_bathrooms:
            params["minBathrooms"] = query.min_bathrooms
        if query.max_bathrooms:
            params["maxBathrooms"] = query.max_bathrooms
        return params

    def _search(self, params: dict[str, Any]) -> dict[str, Any]:
        connection = http.client.HTTPSConnection(self.BASE_HOST, port=443)
        try:
            endpoint_url = "/api/_search"
            response = self._request(
                connection,
                "GET",
                endpoint_url,
                params,
            )
            full_response = copy.deepcopy(response)
            while len(full_response["properties"]) < min(
                int(response["resultCount"].replace(",", "")), self.SEARCH_MAX_RESULTS
            ):
                params = copy.deepcopy(params)
                params["index"] = int(full_response["pagination"]["next"])
                response = self._request(
                    connection,
                    "GET",
                    endpoint_url,
                    params,
                )
                full_response["properties"].extend(response["properties"])
            return full_response
        finally:
            connection.close()

    def _request(
        self,
        connection: http.client.HTTPSConnection,
        method: Literal["GET"],
        url: str,
        parameters: dict[str, Any],
    ) -> Any:
        query_string = urllib.parse.urlencode(parameters, doseq=True)
        urlparse = urllib.parse.urlparse(url)
        urlparse = urlparse._replace(query=query_string)
        url = urllib.parse.urlunparse(urlparse)
        connection.request(
            method,
            url,
            headers={
                "User-Agent": "IAmLookingToRent/0.0.0",
                "Accept-Encoding": "gzip",
                "Accept": "*/*",
                "Connection": "keep-alive",
            },
        )
        http_response = connection.getresponse()
        if http_response.status != http.HTTPStatus.OK:
            raise HTTPError(
                f"HTTP error {http_response.status}: {http_response.reason}"
            )
        raw_response = http_response.read()
        if http_response.getheader("Content-Encoding") == "gzip":
            raw_response = gzip.decompress(raw_response)
        response = json.loads(raw_response)
        return response
