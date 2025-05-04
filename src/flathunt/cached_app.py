import concurrent.futures
import datetime
import logging
import zoneinfo
from collections.abc import Iterable, Iterator
from typing import Optional, Protocol, Union

import tqdm

import rightmove.models
import rightmove.price
import tfl.api
import tfl.cache
import tfl.models
from rightmove import api, property_cache

logger = logging.Logger(__name__)


class SupportsStr(Protocol):
    def __str__(self) -> str: ...


class App:
    def __init__(
        self,
        commute_coordinates: list[tuple[float, float]],
        property_cache: Optional[property_cache.PropertyCache],
        journey_cache: Optional[tfl.cache.Cache],
        tfl_api: tfl.api.Tfl,
        progress_bar: bool,
    ) -> None:
        self._api = api.Rightmove()
        self._property_cache = property_cache
        self._journey_cache = journey_cache
        self._commute_coordinates = commute_coordinates
        self._tfl = tfl_api
        self._progress_bar = progress_bar

    def search(
        self,
        properties: list[rightmove.models.Property],
        max_price: int,
        max_days_since_added: Optional[int],
        journey_coordinates: dict[str, tuple[float, float]],
        max_journey_timedelta: datetime.timedelta,
        min_square_meters: int = 0,
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
        executor = concurrent.futures.ThreadPoolExecutor()
        try:
            futures = [
                executor.submit(
                    lambda p: (
                        p,
                        self._suitable_property(
                            property=p,
                            max_price=max_price,
                            max_days_since_added=max_days_since_added,
                            journey_coordinates=journey_coordinates,
                            max_journey_timedelta=max_journey_timedelta,
                            min_square_meters=min_square_meters,
                        ),
                    ),
                    property,
                )
                for property in new_properties
            ]
            try:
                with tqdm.tqdm(
                    total=len(new_properties),
                    desc="Filtering properties",
                    unit="properties",
                    disable=not self._progress_bar,
                ) as progress_bar:
                    for future in concurrent.futures.as_completed(futures):
                        progress_bar.update(1)
                        property, skip_reason = future.result()
                        if skip_reason:
                            skip_format, *skip_args = skip_reason
                            progress_bar.set_description(
                                str(skip_format) % (*skip_args,)
                            )
                            if not self._progress_bar:
                                logger.info(*skip_reason)
                        else:
                            yield property
            except Exception as exception:
                executor.shutdown(wait=False, cancel_futures=True)
                raise exception
        finally:
            executor.shutdown(wait=True)

    def _suitable_property(
        self,
        property: rightmove.models.Property,
        max_price: int,
        max_days_since_added: Optional[int],
        journey_coordinates: dict[str, tuple[float, float]],
        max_journey_timedelta: datetime.timedelta,
        min_square_meters: int,
    ) -> Optional[Iterable[SupportsStr]]:
        if any(
            (
                property.commercial,
                property.development,
                property.students,
                property.auction,
            )
        ):
            return (
                'Skipping "%s" because it is not a residential property!',
                property.display_address,
            )
        if not property.price:
            return ('Skipping "%s" because it has no price!', property.display_address)
        if property.display_size:
            if property.display_size.endswith(" sq. ft."):
                square_ft = int(
                    property.display_size.removesuffix(" sq. ft.").replace(",", "")
                )
                square_meters = int(square_ft * 0.092903)
                if square_meters < min_square_meters:
                    return (
                        "Property %s (%s %s) at %s is too small (%s sq. ft.)",
                        property.id,
                        property.price.amount if property.price else "N/A",
                        property.price.frequency if property.price else "N/A",
                        property.display_address,
                        square_ft,
                    )
        pcm = rightmove.price.normalize(property.price) or float("inf")
        if pcm > max_price:
            return (
                'Skipping "%s" (%s %s) because it is too expensive!',
                property.display_address,
                property.price.amount,
                property.price.frequency,
            )
        if property.first_visible_date is not None:
            days_since_added = (
                datetime.datetime.now(datetime.timezone.utc)
                - property.first_visible_date.astimezone(datetime.timezone.utc)
            ).days
            if max_days_since_added and days_since_added > max_days_since_added:
                return (
                    'Skipping "%s" (%s %s) because it was added %d days ago!',
                    property.display_address,
                    property.price.amount,
                    property.price.frequency,
                    days_since_added,
                )
        try:
            if not self._check_journey(
                location=(property.location.latitude, property.location.longitude),
                journey_coordinates=journey_coordinates,
                max_journey_timedelta=max_journey_timedelta,
            ):
                return (
                    'Skipping "%s" (%s %s)',
                    property.display_address,
                    property.price.amount,
                    property.price.frequency,
                )
        except tfl.api.HTTPError as error:
            logger.exception(
                'Skipping "%s" (%s %s) because of TFL error: %s',
                property.display_address,
                property.price.amount,
                property.price.frequency,
                error,
            )

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
            if not journeys:
                return False
            min_journey = min(
                journeys,
                key=lambda journey: arrival_datetime.timestamp()
                - journey.departure_datetime.timestamp(),
            )
            min_journey_timedelta = (
                arrival_datetime - min_journey.departure_datetime.astimezone(tzinfo)
            )
            if min_journey_timedelta > max_journey_timedelta:
                return False
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
            journeys = self._tfl(
                from_location=source,
                to_location=destination,
                arrival_datetime=arrival_datetime,
            )
            if self._journey_cache is not None and isinstance(source, tuple):
                self._journey_cache[(source, destination)] = journeys
            return journeys
