import itertools
from collections.abc import Iterable, Sequence
from typing import Literal

from shapely import Point, Polygon

import rightmove.models
import rightmove.price
from flathunt.coords import CommuteDest
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
    """Fetch all Rightmove properties that fall inside the given BNG polygons.

    Tiles are derived from ``bounding_polygon`` to drive the Rightmove search,
    and results are then filtered to only those contained within ``polys``.

    Args:
        polys: Isochrone intersection polygons in BNG (EPSG:27700).
        channel: Rightmove listing channel, either ``"RENT"`` or ``"BUY"``.
        bounding_polygon: WGS84 polygon used to enumerate search tiles.
        cache: Persistent cache for Rightmove map-search responses.

    Returns:
        A deduplicated list of properties located inside at least one of ``polys``.
    """
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
    queries: Sequence[CommuteDest],
) -> list[tuple[rightmove.models.MapProperty, Sequence[int | None]]]:
    """Retain only properties whose commute durations satisfy every query's maximum.

    Args:
        properties: Sequence of properties to filter.
        durations: Per-property commute durations (minutes) for each query,
            aligned with ``properties``. ``None`` indicates an unknown duration.
        queries: Sequence of ``CommuteDest`` values defining each commute
            destination and its time limit.

    Returns:
        A list of ``(property, durations)`` pairs where every duration is
        non-``None`` and within the corresponding query's maximum.
    """
    return [
        (prop, prop_durations)
        for prop, prop_durations in zip(properties, durations, strict=True)
        if all(
            d is not None and d <= query.max_duration
            for d, query in zip(prop_durations, queries, strict=True)
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
    """Filter properties by price, size, images, and floorplan availability.

    Args:
        properties: Iterable of candidate properties.
        min_budget: Minimum acceptable price (monthly rent or purchase price).
        max_budget: Maximum acceptable price (monthly rent or purchase price).
        has_floorplans: If ``True``, exclude properties without a floorplan.
        has_images: If ``True``, exclude properties with fewer than 3 images.
        square_meters: Minimum acceptable floor area in square metres.
        channel: Listing channel used to interpret the price field;
            ``"RENT"`` normalises to a monthly figure, ``"BUY"`` uses the raw amount.

    Returns:
        A list of properties that satisfy all specified criteria.
    """
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
