import asyncio
import json
import logging
import math
from collections.abc import Iterable
from typing import Literal

from shapely import Point, Polygon
from shapely.geometry import box

import rightmove.models
import rightmove.price
import tfl.api
from flathunt.cache import ModelCache
from flathunt.search_utils import check_property_size, fetch_journey_results, get_property_ids_in_area

logger = logging.getLogger(__name__)

TILE_SIZE = 0.02


def get_tiles_covering_polygon(
    polygon: Polygon,
) -> list[tuple[str, list[tuple[float, float]]]]:
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
                # coords as (lat, lon)
                tile_coords = [
                    (lat, lon),
                    (lat + TILE_SIZE, lon),
                    (lat + TILE_SIZE, lon + TILE_SIZE),
                    (lat, lon + TILE_SIZE),
                    (lat, lon),
                ]
                tile_id = f"{lat:.4f}_{lon:.4f}"
                tiles.append((tile_id, tile_coords))
    return tiles


def get_property_ids_in_area_cached(
    map_polygon_boundary: Polygon,
    coords: list[tuple[float, float]],
    channel: Literal["RENT", "BUY"],
    cache: ModelCache[list[rightmove.models.MapProperty]],
) -> list[rightmove.models.MapProperty]:
    shapely_coords = [(lon, lat) for lat, lon in coords]
    search_polygon = Polygon(shapely_coords)
    if not search_polygon.is_valid:
        search_polygon = search_polygon.buffer(0)

    tiles = get_tiles_covering_polygon(map_polygon_boundary)

    selected_tiles = []
    for tile_id, tile_coords in tiles:
        # tile_coords is (lat, lon)
        tile_poly = Polygon([(lon, lat) for lat, lon in tile_coords])
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

        results = [
            asyncio.run(get_property_ids_in_area(tc, channel=channel))
            for _, tc in tiles_to_fetch
        ]

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
    to_froms: list[tuple[float, float, float, float]],
    cache: ModelCache[int | None],
    tfl_api_key: str,
) -> list[int | None]:
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


def filter_properties_by_commute(
    properties: list[rightmove.models.MapProperty],
    queries: list[tuple[float, float, float]],
    journey_cache: ModelCache[int | None],
    tfl_api_key: str,
) -> list[rightmove.models.MapProperty]:
    commute_queries: list[tuple[float, float, float, float]] = [
        (prop.location.longitude, prop.location.latitude, query_lon, query_lat)
        for prop in properties
        for query_lon, query_lat, _ in queries
    ]
    durations = asyncio.run(
        get_properties_journey_duration_cached(commute_queries, journey_cache, tfl_api_key)
    )

    filtered: list[rightmove.models.MapProperty] = []
    for i, prop in enumerate(properties):
        meets_commute = all(
            durations[i * len(queries) + j] is not None
            and durations[i * len(queries) + j] <= max_duration
            for j, (_, _, max_duration) in enumerate(queries)
        )
        if meets_commute:
            filtered.append(prop)
    return filtered
