import gzip
import http
import http.client
import json
from typing import Any
import copy
import urllib.parse
from rightmove import models
from typing import Optional


class HTTPError(Exception): ...


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
        location_id: str,
        max_price: int,
        max_miles_radius: float,
        max_days_since_added: Optional[int],
    ) -> list[models.Property]:
        search_results = self._raw_api.search(
            location_id=location_id,
            max_price=max_price,
            max_miles_radius=max_miles_radius,
            max_days_since_added=max_days_since_added,
        )
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
        location_id: str,
        max_price: int,
        max_miles_radius: float,
        max_days_since_added: Optional[int],
    ) -> dict[str, Any]:
        params = {
            "locationIdentifier": location_id,
            "minBedrooms": 1,
            "maxPrice": max_price,
            "numberOfPropertiesPerPage": 24,
            "radius": max_miles_radius,
            "sortType": 6,  # Most recent.
            "includeLetAgreed": False,
            "viewType": "LIST",
            "dontShow[0]": "houseShare",
            "dontShow[1]": "retirement",
            "dontShow[2]": "student",
            "furnishTypes[0]": "furnished",
            "furnishTypes[1]": "partFurnished",
            "channel": "RENT",
            "areaSizeUnit": "sqm",
            "currencyCode": "GBP",
            "isFetching": False,
        }
        if max_days_since_added is not None:
            params["maxDaysSinceAdded"] = max_days_since_added
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
                params["index"] = len(full_response["properties"])
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
