import requests
from typing import Any
import copy


class Rightmove:
    BASE_URL = "https://www.rightmove.co.uk"

    def search(
        self,
        location_id: str,
        max_price: int,
        max_miles_radius: float,
        max_days_since_added: int | None,
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

    def _search(self, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.BASE_URL}/api/_search"
        reponse = requests.get(url, params=params).json()
        full_reponse = copy.deepcopy(reponse)
        while len(full_reponse["properties"]) < int(reponse["resultCount"]):
            params = copy.deepcopy(params)
            params["index"] = len(full_reponse["properties"])
            reponse = requests.get(url, params=params).json()
            full_reponse["properties"].extend(reponse["properties"])
        return full_reponse

    def property_url(self, property_url: str) -> str:
        return self.BASE_URL + property_url
