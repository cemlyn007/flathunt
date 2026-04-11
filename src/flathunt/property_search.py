import asyncio
import json
import logging
import math
from collections.abc import Sequence
from typing import Literal

from shapely import Point, Polygon
from shapely.geometry import box

import rightmove.models
import tfl.api
from flathunt.coords import CommuteDest, LatLon
from flathunt.cache import ModelCache
from flathunt.search_utils import (
    fetch_journey_results,
    get_property_ids_in_area,
)

logger = logging.getLogger(__name__)

TILE_SIZE = 0.02
_RIGHTMOVE_CONCURRENCY = 3


def get_tiles_covering_polygon(
    polygon: Polygon,
) -> list[tuple[str, list[LatLon]]]:
    """Enumerate fixed-size WGS84 tiles that intersect a polygon.

    The map is divided into a regular grid of ``TILE_SIZE`` × ``TILE_SIZE``
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


def get_property_ids_in_area_cached(
    map_polygon_boundary: Polygon,
    coords: Sequence[LatLon],
    channel: Literal["RENT", "BUY"],
    cache: ModelCache[list[rightmove.models.MapProperty]],
) -> list[rightmove.models.MapProperty]:
    """Fetch Rightmove properties within a polygon, using a tile cache to avoid redundant requests.

    ``map_polygon_boundary`` is tiled and each tile is looked up in ``cache``
    before falling back to the Rightmove API. Results are deduplicated and
    filtered to only those contained within the search polygon derived from
    ``coords``.

    Args:
        map_polygon_boundary: WGS84 polygon defining the overall map boundary
            used to generate search tiles.
        coords: Exterior ring of the search area as ``LatLon`` values in WGS84.
        channel: Rightmove listing channel, either ``"RENT"`` or ``"BUY"``.
        cache: Persistent tile-level cache for Rightmove responses.

    Returns:
        A deduplicated list of properties whose locations fall inside the
        polygon described by ``coords``.
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

    all_properties = []
    tiles_to_fetch = []

    for tile_id, tile_coords in selected_tiles:
        key = json.dumps(
            {"tile_id": tile_id, "channel": channel, "tile_size": TILE_SIZE}
        )
        try:
            cached_props = cache.get(key)
            all_properties.extend(cached_props)
        except KeyError:
            tiles_to_fetch.append((key, tile_coords))

    if tiles_to_fetch:
        logger.info(f"Fetching {len(tiles_to_fetch)} tiles from Rightmove.")

        semaphore = asyncio.Semaphore(_RIGHTMOVE_CONCURRENCY)

        async def _fetch_all() -> list[list[rightmove.models.MapProperty]]:
            return list(
                await asyncio.gather(
                    *[
                        get_property_ids_in_area(
                            tc, channel=channel, semaphore=semaphore
                        )
                        for _, tc in tiles_to_fetch
                    ]
                )
            )

        results = asyncio.run(_fetch_all())

        cache_updates = []
        for (key, _), props in zip(tiles_to_fetch, results, strict=True):
            cache_updates.append((key, props))
            all_properties.extend(props)

        cache.update(cache_updates)

    # Deduplicate by ID
    unique_properties: list[rightmove.models.MapProperty] = []
    seen_ids = set()
    for p in all_properties:
        if p.id not in seen_ids:
            unique_properties.append(p)
            seen_ids.add(p.id)

    # Filter by original polygon
    return [
        p
        for p in unique_properties
        if search_polygon.contains(Point(p.location.longitude, p.location.latitude))
    ]


async def get_properties_journey_duration_cached(
    to_froms: Sequence[tuple[float, float, float, float]],
    cache: ModelCache[int | None],
    tfl_api_key: str,
) -> list[int | None]:
    """Fetch TfL journey durations for a list of origin/destination pairs, using a cache.

    Cache hits are returned immediately; misses are fetched concurrently from the
    TfL API and then stored.

    Args:
        to_froms: A list of ``(from_lon, from_lat, to_lon, to_lat)`` tuples.
        cache: Persistent cache mapping journey keys to durations in minutes.
        tfl_api_key: TfL API application key.

    Returns:
        A list of journey durations (minutes) aligned with ``to_froms``.
        ``None`` indicates a failed or unavailable journey.
    """
    durations: list[int | None] = []
    to_fetch = []
    fetch_indices = []
    for i, (lon, lat, query_lon, query_lat) in enumerate(to_froms):
        key = json.dumps({"from": (lon, lat), "to": (query_lon, query_lat)})
        try:
            duration = cache.get(key)
            durations.append(duration)
            logger.info(
                "Journey duration from (%s, %s) to (%s, %s) fetched from cache.",
                lon,
                lat,
                query_lon,
                query_lat,
            )
        except KeyError:
            to_fetch.append((lon, lat, query_lon, query_lat))
            fetch_indices.append(i)
            durations.append(None)  # Placeholder

    if to_fetch:
        client = tfl.api.Tfl(app_key=tfl_api_key)
        tasks = [
            fetch_journey_results(client, lon, lat, query_lon, query_lat)
            for lon, lat, query_lon, query_lat in to_fetch
        ]
        results = await asyncio.gather(*tasks)
        cache_updates = []
        for idx, duration in zip(fetch_indices, results, strict=True):
            durations[idx] = duration
            lon, lat, query_lon, query_lat = to_froms[idx]
            key = json.dumps({"from": (lon, lat), "to": (query_lon, query_lat)})
            cache_updates.append((key, duration))
        cache.update(cache_updates)

    return durations


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
    flat_durations = await get_properties_journey_duration_cached(
        flat_to_froms, cache, tfl_api_key
    )
    n = len(queries)
    return [flat_durations[i * n : (i + 1) * n] for i in range(len(properties))]
