import asyncio
import logging
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import dagster as dg
from shapely.geometry import box
from shapely.geometry.polygon import Polygon
from shapely.ops import unary_union

import rightmove.models
from flathunt.cache import ModelCache
from flathunt.filters import fetch_properties_within_optimal_regions
from flathunt.geometry import poly_bng_to_wgs84, poly_bng_to_wgs84_coords
from flathunt.property_search import (
    DEFAULT_ACTIVE_PROPERTY_TILE_CACHE_TTL,
    DEFAULT_INACTIVE_PROPERTY_TILE_CACHE_TTL,
    DEFAULT_PROPERTY_TILE_CACHE_RETENTION_TTL,
    count_tiles,
)
from flathunt.search_utils import check_property_size

logger = logging.getLogger(__name__)

_SEEN_IDS_DB = "seen_property_ids.db"


def _open_seen_ids_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS seen_ids (property_id INTEGER PRIMARY KEY)"
    )
    conn.commit()
    return conn


def _load_seen_ids(path: Path) -> frozenset[int]:
    with _open_seen_ids_db(path) as conn:
        rows = conn.execute("SELECT property_id FROM seen_ids").fetchall()
    return frozenset(row[0] for row in rows)


def _save_seen_ids(path: Path, ids: Iterable[int]) -> None:
    with _open_seen_ids_db(path) as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO seen_ids (property_id) VALUES (?)",
            [(pid,) for pid in ids],
        )


class Config(dg.Config):
    channel: Literal["RENT", "BUY"] = "BUY"
    # For BUY: purchase price in £. For RENT: monthly rent in £.
    min_budget: float = 100_000
    max_budget: float = 2_000_000
    has_floorplans: bool = False
    has_images: bool = False
    min_square_meters: float = 0.0
    cache_data_dir: str = "cache"
    active_property_tile_cache_ttl_hours: float = (
        DEFAULT_ACTIVE_PROPERTY_TILE_CACHE_TTL / 3600
    )
    inactive_property_tile_cache_ttl_hours: float = (
        DEFAULT_INACTIVE_PROPERTY_TILE_CACHE_TTL / 3600
    )
    property_tile_cache_retention_hours: float = (
        DEFAULT_PROPERTY_TILE_CACHE_RETENTION_TTL / 3600
    )


def _hours_to_seconds(name: str, hours: float) -> int:
    if hours <= 0:
        raise ValueError(f"{name} must be > 0 hours, got {hours!r}.")
    return int(hours * 3600)


@dg.asset
def candidate_properties(
    context: dg.AssetExecutionContext,
    config: Config,
    isochrone_intersection: list[Polygon],
) -> list[rightmove.models.MapProperty]:
    """Fetch and filter Rightmove properties within the isochrone intersection area.

    Tiles the bounding box of the intersection polygons and queries Rightmove
    for properties within each tile using the listing search endpoint, sorted
    by most-recent.  Pagination stops early whenever a full page consists
    entirely of property IDs seen in previous runs, minimising API requests on
    repeat pipeline executions.

    Server-side price filtering (``min_budget``/``max_budget``) is forwarded to
    the Rightmove API.  Feature filtering (floor area, image count, floorplan
    availability) is applied as properties arrive, before accumulation.
    Results are cached per tile in a SQLite database.

    Args:
        context: Dagster asset execution context, used for progress logging.
        config: Asset configuration: channel (RENT/BUY), price range, feature
            flags, size threshold, and the path to the cache directory.
        isochrone_intersection: BNG Polygons from the ``isochrone_intersection``
            asset defining the search area.

    Returns:
        A list of :class:`rightmove.models.MapProperty` objects that satisfy
        all configured constraints and lie within the intersection area.
    """
    non_empty = [p for p in isochrone_intersection if not p.is_empty]
    if not non_empty:
        logger.warning("Isochrone intersection is empty; no properties to fetch.")
        return []

    wgs84_polys = [poly_bng_to_wgs84(p) for p in non_empty]
    bounding_polygon = box(*unary_union(wgs84_polys).bounds)

    cache_path = Path(config.cache_data_dir) / "property_locations_cache.db"
    logger.info("Opening property locations cache at %s.", cache_path)
    active_tile_ttl = _hours_to_seconds(
        "active_property_tile_cache_ttl_hours",
        config.active_property_tile_cache_ttl_hours,
    )
    inactive_tile_ttl = _hours_to_seconds(
        "inactive_property_tile_cache_ttl_hours",
        config.inactive_property_tile_cache_ttl_hours,
    )
    retention_ttl = _hours_to_seconds(
        "property_tile_cache_retention_hours",
        config.property_tile_cache_retention_hours,
    )
    if active_tile_ttl > inactive_tile_ttl:
        raise ValueError(
            "active_property_tile_cache_ttl_hours must be <= "
            "inactive_property_tile_cache_ttl_hours."
        )
    if inactive_tile_ttl > retention_ttl:
        raise ValueError(
            "property_tile_cache_retention_hours must be >= "
            "inactive_property_tile_cache_ttl_hours."
        )
    cache: ModelCache[list[rightmove.models.MapProperty]] = ModelCache(
        list[rightmove.models.MapProperty], cache_path, ttl=retention_ttl
    )

    seen_ids_path = Path(config.cache_data_dir) / _SEEN_IDS_DB
    seen_ids = _load_seen_ids(seen_ids_path)
    logger.info("Loaded %d previously seen property ID(s).", len(seen_ids))

    def predicate(p: rightmove.models.MapProperty) -> bool:
        return (
            p.property_url is not None
            and check_property_size(p, config.min_square_meters)
            and ((p.number_of_images or 0) > 2 or not config.has_images)
            and ((p.number_of_floorplans or 0) > 0 or not config.has_floorplans)
        )

    logger.info(
        "Fetching %s properties within %d intersection polygon(s).",
        config.channel,
        len(non_empty),
    )

    total = sum(
        count_tiles(bounding_polygon, poly_bng_to_wgs84_coords(poly))
        for poly in non_empty
    )

    async def _fetch() -> list[rightmove.models.MapProperty]:
        all_properties = []
        done = 0
        async for props in fetch_properties_within_optimal_regions(
            non_empty,
            config.channel,
            bounding_polygon,
            cache,
            min_price=int(config.min_budget),
            max_price=int(config.max_budget),
            seen_ids=seen_ids,
            predicate=predicate,
            active_tile_ttl=active_tile_ttl,
            inactive_tile_ttl=inactive_tile_ttl,
        ):
            all_properties.extend(props)
            done += 1
            context.log.info("Tile %d / %d fetched.", done, total)
        seen: set[int] = set()
        result = []
        for p in all_properties:
            if p.id not in seen:
                seen.add(p.id)
                result.append(p)
        return result

    properties = asyncio.run(_fetch())
    logger.info("Retrieved %d propert(ies) after filtering.", len(properties))

    _save_seen_ids(seen_ids_path, (p.id for p in properties))
    logger.info("Updated seen property IDs in %s.", seen_ids_path)

    return properties
