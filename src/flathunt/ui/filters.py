import itertools
from collections.abc import Iterable, Sequence
from typing import Literal

from shapely import Point, Polygon

import rightmove.models
import rightmove.price
from flathunt.ui.cache import ModelCache
from flathunt.geometry import poly_bng_to_wgs84, poly_bng_to_wgs84_coords
from flathunt.ui.property_search import get_property_ids_in_area_cached
from flathunt.ui.search_utils import check_property_size


def fetch_properties_within_optimal_regions(
    polys: list[Polygon],
    channel: Literal["RENT", "BUY"],
    bounding_polygon: Polygon,
    cache: ModelCache[list[rightmove.models.MapProperty]],
) -> list[rightmove.models.MapProperty]:
    non_empty = [poly for poly in polys if not poly.is_empty]
    locations = list(
        itertools.chain.from_iterable(
            get_property_ids_in_area_cached(
                bounding_polygon, poly_bng_to_wgs84_coords(poly), channel, cache
            )
            for poly in non_empty
        )
    )
    polys_wgs84 = [poly_bng_to_wgs84(poly) for poly in non_empty]
    return [
        loc
        for loc in locations
        if any(
            poly.contains(Point(loc.location.longitude, loc.location.latitude))
            for poly in polys_wgs84
        )
    ]


def filter_by_commute(
    properties: Sequence[rightmove.models.MapProperty],
    durations: Sequence[Sequence[int | None]],
    queries: Sequence[tuple[float, float, float]],
) -> list[tuple[rightmove.models.MapProperty, Sequence[int | None]]]:
    return [
        (prop, prop_durations)
        for prop, prop_durations in zip(properties, durations, strict=True)
        if all(
            d is not None and d <= max_duration
            for d, (_, _, max_duration) in zip(prop_durations, queries, strict=True)
        )
    ]


def filter_properties_by_budget_and_features(
    properties: Iterable[rightmove.models.MapProperty],
    min_budget: float,
    max_budget: float,
    has_floorplans: bool,
    has_images: bool,
    square_meters: float,
    channel: Literal["RENT", "BUY"],
) -> list[rightmove.models.MapProperty]:
    return [
        p
        for p in properties
        if p.property_url is not None
        and check_property_size(p, square_meters)
        and p.price is not None
        and (
            min_budget <= (rightmove.price.normalize(p.price) or 0) <= max_budget
            if channel == "RENT"
            else min_budget <= (p.price.amount or 0) <= max_budget
        )
        and ((p.number_of_images or 0) > 2 or not has_images)
        and ((p.number_of_floorplans or 0) > 0 or not has_floorplans)
    ]
