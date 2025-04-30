from collections.abc import Iterator
import zoneinfo
from rightmove import api, property_cache
import rightmove.models
import tfl.cache
import rightmove.price
import datetime
import tfl.api
import logging
import tfl.models
from typing import Optional, Union

logger = logging.Logger(__name__)


class App:
    def __init__(
        self,
        commute_coordinates: list[tuple[float, float]],
        property_cache: Optional[property_cache.PropertyCache],
        journey_cache: Optional[tfl.cache.Cache],
        tfl_app_key: str,
    ) -> None:
        self._api = api.Rightmove()
        self._property_cache = property_cache
        self._journey_cache = journey_cache
        self._commute_coordinates = commute_coordinates
        self._tfl_app_key = tfl_app_key

    def search(
        self,
        properties: list[rightmove.models.Property],
        max_price: int,
        max_days_since_added: Optional[int],
        journey_coordinates: dict[str, tuple[float, float]],
        max_journey_timedelta: datetime.timedelta,
    ) -> Iterator[rightmove.models.Property]:
        logger.info("Search returned %d properties", len(properties))
        new_properties = [
            property
            for property in properties
            if not self._property_cache
            or not self._property_cache.contains_property_id(property.id)
        ]
        logger.info(
            "After filtering cached properties, returned %d properties",
            len(new_properties),
        )
        for index, property in enumerate(new_properties):
            if any(
                (
                    property.commercial,
                    property.development,
                    property.students,
                    property.auction,
                )
            ):
                logger.info(
                    'Skipping "%s" because it is not a residential property!',
                    property.display_address,
                )
                continue

            if not property.price:
                logger.info(
                    'Skipping "%s" because it has no price!', property.display_address
                )
                continue

            pcm = rightmove.price.normalize(property.price) or float("inf")
            if pcm > max_price:
                logger.info(
                    'Skipping "%s" (%s %s) because it is too expensive!',
                    property.display_address,
                    property.price.amount,
                    property.price.frequency,
                )
                continue

            if property.first_visible_date is not None:
                days_since_added = (
                    datetime.datetime.now(datetime.timezone.utc)
                    - property.first_visible_date.astimezone(datetime.timezone.utc)
                ).days
                if max_days_since_added and days_since_added > max_days_since_added:
                    logger.info(
                        'Skipping "%s" (%s %s) because it was added %d days ago!',
                        property.display_address,
                        property.price.amount,
                        property.price.frequency,
                        days_since_added,
                    )
                    continue

            logger.info('Checking journey from "%s"', property.display_address)
            try:
                if not self._check_journey(
                    location=(property.location.latitude, property.location.longitude),
                    journey_coordinates=journey_coordinates,
                    max_journey_timedelta=max_journey_timedelta,
                ):
                    logger.info(
                        'Skipping "%s" (%s %s)',
                        property.display_address,
                        property.price.amount,
                        property.price.frequency,
                    )
                    continue
            except tfl.api.HTTPError as error:
                logger.exception(
                    'Skipping "%s" (%s %s) because of TFL error: %s',
                    property.display_address,
                    property.price.amount,
                    property.price.frequency,
                    error,
                )
                continue
            logger.info(
                'Showing "%s" (%s %s)',
                property.display_address,
                property.price.amount,
                property.price.frequency,
            )
            yield property

    def _check_journey(
        self,
        location: Union[tuple[float, float], str],
        journey_coordinates: dict[str, tuple[float, float]],
        max_journey_timedelta: datetime.timedelta,
    ) -> bool:
        tzinfo = zoneinfo.ZoneInfo("Europe/London")
        arrival_datetime = tfl.api.get_next_datetime(
            datetime.time(9, 0, 0, 0, tzinfo=tzinfo)
        )
        for location_name, journey_coordinate in journey_coordinates.items():
            journeys = self._get_journeys(
                location, journey_coordinate, arrival_datetime
            )
            logger.info("Location: %s, Journey: %d", location_name, len(journeys))
            min_journey = min(
                journeys,
                key=lambda journey: arrival_datetime - journey.departure_datetime,
            )
            min_journey_timedelta = arrival_datetime - min_journey.departure_datetime
            if min_journey_timedelta > max_journey_timedelta:
                logger.info(
                    "Unacceptable journeys (%s, %s)",
                    location_name,
                    min_journey_timedelta,
                )
                return False
            logger.info(
                "Acceptable journey (%s, %s, %s)",
                location_name,
                min_journey.mode.value,
                min_journey_timedelta,
            )
        logger.info("Acceptable journeys")
        return True

    def _get_journeys(
        self,
        source: Union[tuple[float, float], str],
        destination: tuple[float, float],
        arrival_datetime: datetime.datetime,
    ) -> list[tfl.models.Journey]:
        if (
            self._journey_cache is not None
            and isinstance(source, tuple)
            and (source, destination) in self._journey_cache
        ):
            return self._journey_cache[(source, destination)]
        else:
            tfl_api = tfl.api.Tfl(
                from_location=source,
                to_location=destination,
                app_key=self._tfl_app_key,
                arrival_datetime=arrival_datetime,
            )
            journeys = tfl_api()
            if self._journey_cache is not None and isinstance(source, tuple):
                self._journey_cache[(source, destination)] = journeys
            return journeys
