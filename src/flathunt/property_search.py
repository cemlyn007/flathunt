import asyncio
import json
import logging
import math
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Literal

from shapely import Point, Polygon
from shapely.geometry import box

import rightmove.models
import tfl.api
from flathunt.cache import ModelCache
from flathunt.coords import CommuteDest, LatLon
from flathunt.search_utils import (
    fetch_journey_results,
    get_property_ids_in_area,
)

logger = logging.getLogger(__name__)

TILE_SIZE = 0.02
_RIGHTMOVE_CONCURRENCY = 3


# ============================================================================
# Tile utilities: low-level geometry and tile enumeration
# ============================================================================


def get_tiles_covering_polygon(
    polygon: Polygon,
) -> list[tuple[str, list[LatLon]]]:
    """Enumerate fixed-size WGS84 tiles that intersect a polygon.

    The map is divided into a regular grid of ``TILE_SIZE`` x ``TILE_SIZE``
    degree cells. Only cells that intersect ``polygon`` are returned.

    Args:
        polygon: A Shapely Polygon in WGS84 (EPSG:4326).

    Returns:
        A list of ``(tile_id, tile_coords)`` pairs, where ``tile_id`` is a
        string key derived from the tile's south-west corner and ``tile_coords``
        is a list of five ``LatLon`` values forming the closed tile boundary.
    """
    min_lon, min_lat, max_lon, max_lat = polygon.bounds

    start_lon_idx = math.floor(min_lon / TILE_SIZE)
    end_lon_idx = math.ceil(max_lon / TILE_SIZE)
    start_lat_idx = math.floor(min_lat / TILE_SIZE)
    end_lat_idx = math.ceil(max_lat / TILE_SIZE)

    tiles = []
    for lon_idx in range(start_lon_idx, end_lon_idx):
        for lat_idx in range(start_lat_idx, end_lat_idx):
            lon = lon_idx * TILE_SIZE
            lat = lat_idx * TILE_SIZE
            tile_poly = box(lon, lat, lon + TILE_SIZE, lat + TILE_SIZE)
            if polygon.intersects(tile_poly):
                tile_coords = [
                    LatLon(lat=lat, lon=lon),
                    LatLon(lat=lat + TILE_SIZE, lon=lon),
                    LatLon(lat=lat + TILE_SIZE, lon=lon + TILE_SIZE),
                    LatLon(lat=lat, lon=lon + TILE_SIZE),
                    LatLon(lat=lat, lon=lon),
                ]
                tile_id = f"{lat:.4f}_{lon:.4f}"
                tiles.append((tile_id, tile_coords))
    return tiles


def count_tiles(
    map_polygon_boundary: Polygon,
    coords: Sequence[LatLon],
) -> int:
    """Return the total number of tiles that intersect the search area.

    Args:
        map_polygon_boundary: WGS84 polygon used to enumerate search tiles.
        coords: Exterior ring of the search area as ``LatLon`` values in WGS84.

    Returns:
        The number of tiles that overlap the search polygon.
    """
    search_polygon = Polygon([(c.lon, c.lat) for c in coords])
    if not search_polygon.is_valid:
        search_polygon = search_polygon.buffer(0)
    tiles = get_tiles_covering_polygon(map_polygon_boundary)
    return sum(
        1
        for _, tile_coords in tiles
        if search_polygon.intersects(Polygon([(c.lon, c.lat) for c in tile_coords]))
    )


# ============================================================================
# Property search: cached queries for Rightmove property data
# ============================================================================


async def get_property_ids_in_area_cached(
    map_polygon_boundary: Polygon,
    coords: Sequence[LatLon],
    channel: Literal["RENT", "BUY"],
    cache: ModelCache[list[rightmove.models.MapProperty]],
    *,
    min_price: int | None = None,
    max_price: int | None = None,
    seen_ids: frozenset[int] = frozenset(),
    predicate: Callable[[rightmove.models.MapProperty], bool] | None = None,
) -> AsyncIterator[list[rightmove.models.MapProperty]]:
    """Async generator yielding per-tile property lists as each tile is resolved.

    Cache hits are yielded immediately; misses are fetched concurrently via the
    Rightmove API and yielded as they complete.  Properties in each yielded list
    are filtered to those contained within the search polygon derived from
    ``coords``, and to those satisfying ``predicate`` (if provided).

    Args:
        map_polygon_boundary: WGS84 polygon defining the overall map boundary
            used to generate search tiles.
        coords: Exterior ring of the search area as ``LatLon`` values in WGS84.
        channel: Rightmove listing channel, either ``"RENT"`` or ``"BUY"``.
        cache: Persistent tile-level cache for Rightmove responses.
        min_price: Minimum price forwarded to the Rightmove API.
        max_price: Maximum price forwarded to the Rightmove API.
        seen_ids: Property IDs from previous runs used for early-exit on cache
            misses.  Not included in the cache key.
        predicate: Optional filter applied to each property after retrieval
            (from cache or API).  Not included in the cache key.

    Yields:
        A list of properties located inside the search polygon for each tile.
    """
    search_polygon = Polygon([(c.lon, c.lat) for c in coords])
    if not search_polygon.is_valid:
        search_polygon = search_polygon.buffer(0)

    tiles = get_tiles_covering_polygon(map_polygon_boundary)

    selected_tiles = []
    for tile_id, tile_coords in tiles:
        tile_poly = Polygon([(c.lon, c.lat) for c in tile_coords])
        if search_polygon.intersects(tile_poly):
            selected_tiles.append((tile_id, tile_coords))

    tiles_to_fetch = []
    for tile_id, tile_coords in selected_tiles:
        key = json.dumps(
            {
                "tile_id": tile_id,
                "channel": channel,
                "tile_size": TILE_SIZE,
                "min_price": min_price,
                "max_price": max_price,
            }
        )
        try:
            cached_props = cache.get(key)
            yield [
                p
                for p in cached_props
                if search_polygon.contains(
                    Point(p.location.longitude, p.location.latitude)
                )
                and (predicate is None or predicate(p))
            ]
        except KeyError:
            tiles_to_fetch.append((key, tile_coords))

    if tiles_to_fetch:
        semaphore = asyncio.Semaphore(_RIGHTMOVE_CONCURRENCY)

        async def _fetch_one(
            key: str, tile_coords: list[LatLon]
        ) -> list[rightmove.models.MapProperty]:
            props = await get_property_ids_in_area(
                tile_coords,
                channel=channel,
                semaphore=semaphore,
                min_price=min_price,
                max_price=max_price,
                seen_ids=seen_ids,
            )
            cache.update([(key, props)])
            return [
                p
                for p in props
                if search_polygon.contains(
                    Point(p.location.longitude, p.location.latitude)
                )
                and (predicate is None or predicate(p))
            ]

        for coro in asyncio.as_completed(
            [_fetch_one(k, tc) for k, tc in tiles_to_fetch]
        ):
            yield await coro


# ============================================================================
# Commute search: cached queries for TfL journey duration data
# ============================================================================


async def get_properties_journey_duration_cached(
    to_froms: Sequence[tuple[float, float, float, float]],
    cache: ModelCache[int | None],
    tfl_api_key: str,
) -> AsyncIterator[tuple[int, int | None]]:
    """Async generator yielding ``(index, duration)`` pairs as results are resolved.

    Cache hits are yielded first in index order; misses are fetched concurrently
    and yielded as they complete.

    Args:
        to_froms: A list of ``(from_lon, from_lat, to_lon, to_lat)`` tuples.
        cache: Persistent cache mapping journey keys to durations in minutes.
        tfl_api_key: TfL API application key.

    Yields:
        ``(index, duration)`` pairs aligned with ``to_froms``. Duration is
        ``None`` if the journey is unavailable.
    """
    to_fetch: list[tuple[int, float, float, float, float]] = []
    for i, (lon, lat, query_lon, query_lat) in enumerate(to_froms):
        key = json.dumps({"from": (lon, lat), "to": (query_lon, query_lat)})
        try:
            yield i, cache.get(key)
        except KeyError:
            to_fetch.append((i, lon, lat, query_lon, query_lat))

    if to_fetch:
        client = tfl.api.Tfl(app_key=tfl_api_key)

        async def _fetch_one(
            i: int, lon: float, lat: float, query_lon: float, query_lat: float
        ) -> tuple[int, int | None]:
            duration = await fetch_journey_results(
                client, lon, lat, query_lon, query_lat
            )
            key = json.dumps({"from": (lon, lat), "to": (query_lon, query_lat)})
            cache.update([(key, duration)])
            return i, duration

        for coro in asyncio.as_completed([_fetch_one(*row) for row in to_fetch]):
            yield await coro


# ============================================================================
# High-level public APIs
# ============================================================================


async def get_commute_durations(
    properties: Sequence[rightmove.models.MapProperty],
    queries: Sequence[CommuteDest],
    cache: ModelCache[int | None],
    tfl_api_key: str,
) -> list[list[int | None]]:
    """Compute TfL commute durations from each property to each query destination.

    Args:
        properties: List of properties whose commute times are required.
        queries: List of ``CommuteDest`` values defining commute destinations.
        cache: Persistent cache for journey durations.
        tfl_api_key: TfL API application key.

    Returns:
        A list aligned with ``properties``. Each element is a list of durations
        (minutes) aligned with ``queries``. ``None`` indicates an unavailable
        journey.
    """
    flat_to_froms: list[tuple[float, float, float, float]] = [
        (prop.location.longitude, prop.location.latitude, query.lon, query.lat)
        for prop in properties
        for query in queries
    ]
    results: list[int | None] = [None] * len(flat_to_froms)
    async for idx, duration in get_properties_journey_duration_cached(
        flat_to_froms, cache, tfl_api_key
    ):
        results[idx] = duration
    n = len(queries)
    return [results[i * n : (i + 1) * n] for i in range(len(properties))]
