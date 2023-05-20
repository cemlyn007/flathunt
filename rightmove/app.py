from typing import Any
from rightmove import api, property_cache
import webbrowser
import sys


class App:
    def __init__(
        self,
        cache_file_path: str,
        commute_coordinates: list[tuple[float, float]],
        reset_cache: bool,
    ) -> None:
        self._api = api.Rightmove()
        self._cache = property_cache.PropertyCache(cache_file_path, reset_cache)
        self._commute_coordinates = commute_coordinates

    def search(
        self,
        location_id: str,
        max_price: int,
        max_miles_radius: float,
        max_days_since_added: int | None,
    ) -> None:
        response = self._api.search(
            location_id, max_price, max_miles_radius, max_days_since_added
        )
        properties = response["properties"]
        new_properties = [
            property
            for property in properties
            if not self._cache.contains_property_id(property["id"])
        ]
        for property in new_properties:
            self._show(property)
            if property != properties[-1]:
                input("Press enter for next property...", flush=True)

            self._cache.add(property)

    def _show(self, property: dict[str, Any]) -> None:
        self._show_advert(property)
        for commute_coordinate in self._commute_coordinates:
            if self._skip():
                break
            # else...
            self._show_commute(property, commute_coordinate)

    def _show_advert(self, property: dict[str, Any]) -> None:
        url = self._api.property_url(property["propertyUrl"])
        webbrowser.open_new_tab(url)

    def _show_commute(
        self, property: dict[str, Any], start_coordinate: tuple[float, float]
    ) -> None:
        saddr = ",".join(map(str, start_coordinate))
        daddr = ",".join(
            map(
                str,
                [
                    property["location"]["latitude"],
                    property["location"]["longitude"],
                ],
            )
        )
        if sys.platform == "darwin":
            map_url = f"https://maps.apple.com/?saddr={saddr}&daddr={daddr}&dirflg=r"
        else:
            map_url = f"https://www.google.com/maps/?saddr={saddr}&daddr={daddr}&directionsmode=transit"
        webbrowser.open_new_tab(map_url)

    def _skip(self) -> bool:
        ans = input('Press "s" to skip, anything else is continue: ')
        return ans == "s"
