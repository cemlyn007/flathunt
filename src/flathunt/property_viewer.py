import logging
import random
import time
import webbrowser

import flathunt.map
import rightmove.api
from rightmove import models

logger = logging.Logger(__name__)


def _random_sleep() -> None:
    """Sleep for a random time between 1 and 3 seconds."""
    time.sleep(1 + (2 * random.random()))


class Viewer:
    def __init__(
        self,
        commute_coordinates: list[tuple[float, float]],
    ) -> None:
        self._commute_coordinates = commute_coordinates

    def __call__(self, property: models.Property) -> None:
        self._show(property)

    def _show(self, property: models.Property) -> None:
        self._show_advert(property)
        for commute_coordinate in self._commute_coordinates:
            self._show_route(property, commute_coordinate)

    def _show_advert(self, property: models.Property) -> None:
        # Some properties don't have a URL.
        if property.property_url:
            url = rightmove.api.property_url(property.property_url)
            webbrowser.open_new_tab(url)
            _random_sleep()

    def _show_route(
        self, property: models.Property, start_coordinate: tuple[float, float]
    ) -> None:
        destination = (
            property.location.latitude,
            property.location.longitude,
        )
        map_url = flathunt.map.url(start_coordinate, destination)
        webbrowser.open_new_tab(map_url)
        _random_sleep()

    def _skip(self) -> bool:
        ans = input('Press "s" to skip, anything else is continue: ')
        return ans == "s"

    def _wait(self, message: str) -> None:
        input(" ".join((message, "Press enter to continue...")))
