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
    MOST_RECENT = 6


class SearchQuery(pydantic.BaseModel):
    location_identifier: str
    min_bedrooms: int
    max_price: int
    number_of_properties_per_page: int
    radius: float
    "In Miles."
    sort_type: SortType
    include_let_agreed: bool
    view_type: Literal["LIST"]
    dont_show: list[Literal["houseShare", "retirement", "student", "commercial"]]
    furnish_types: list[Literal["furnished", "partFurnished", "unfurnished"]]
    channel: Literal["RENT", "BUY"]
    area_size_unit: Literal["sqft", "sqm"]
    currency_code: Literal["GBP"]
    is_fetching: bool
    max_days_since_added: Optional[int]


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
        params = {
            "locationIdentifier": query.location_identifier,
            "minBedrooms": query.min_bedrooms,
            "maxPrice": query.max_price,
            "numberOfPropertiesPerPage": query.number_of_properties_per_page,
            "radius": query.radius,
            "sortType": query.sort_type,
            "includeLetAgreed": query.include_let_agreed,
            "viewType": query.view_type,
        }
        for index, value in enumerate(query.dont_show):
            params[f"dontShow[{index}]"] = value
        for index, value in enumerate(query.furnish_types):
            params[f"furnishTypes[{index}]"] = value
        params.update(
            {
                "channel": query.channel,
                "areaSizeUnit": query.area_size_unit,
                "currencyCode": query.currency_code,
                "isFetching": query.is_fetching,
            }
        )
        if query.max_days_since_added is not None:
            params["maxDaysSinceAdded"] = query.max_days_since_added
        return self._search(params)

    def property_url(self, property_url: str) -> str:
        return f"https://{self.BASE_HOST}{property_url}"

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
        method: str,
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
