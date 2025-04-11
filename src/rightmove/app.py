from rightmove import api, property_cache, models
import webbrowser
import sys
from typing import Optional


class App:
    def __init__(
        self,
        commute_coordinates: list[tuple[float, float]],
        cache: Optional[property_cache.PropertyCache],
    ) -> None:
        self._api = api.Rightmove()
        self._cache = cache
        self._commute_coordinates = commute_coordinates

    def search(
        self,
        query: api.SearchQuery,
    ) -> None:
        properties = self._api.search(query)
        new_properties = [
            property
            for property in properties
            if not self._cache or not self._cache.contains_property_id(property.id)
        ]
        for index, property in enumerate(new_properties):
            self._show(property)
            if index != len(new_properties) - 1:
                self._wait("Press enter for next property...")

            if self._cache:
                self._cache.add(property.model_dump())

    def _show(self, property: models.Property) -> None:
        self._show_advert(property)
        if not self._commute_coordinates or self._skip():
            return
        # else...
        for index, commute_coordinate in enumerate(self._commute_coordinates):
            self._show_route(property, commute_coordinate)
            if index != len(self._commute_coordinates) - 1:
                self._wait("Press enter for next commute location...")

    def _show_advert(self, property: models.Property) -> None:
        # Some properties don't have a URL.
        if property.property_url:
            url = self._api.property_url(property.property_url)
            webbrowser.open_new_tab(url)

    def _show_route(
        self, property: models.Property, start_coordinate: tuple[float, float]
    ) -> None:
        destination = (
            property.location.latitude,
            property.location.longitude,
        )
        map_url = get_map_url(start_coordinate, destination)
        webbrowser.open_new_tab(map_url)

    def _skip(self) -> bool:
        ans = input('Press "s" to skip, anything else is continue: ')
        return ans == "s"

    def _wait(self, message: str) -> None:
        input(" ".join((message, "Press enter to continue...")))


def get_map_url(source: tuple[float, float], destination: tuple[float, float]) -> str:
    saddr = ",".join(map(str, source))
    daddr = ",".join(map(str, destination))
    if sys.platform == "darwin":
        map_url = f"https://maps.apple.com/?saddr={saddr}&daddr={daddr}&dirflg=r"
    else:
        map_url = f"https://www.google.com/maps/?saddr={saddr}&daddr={daddr}&directionsmode=transit"
    return map_url
