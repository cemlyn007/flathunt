import logging
from pathlib import Path
from typing import Literal

import dagster as dg
from shapely.geometry import box
from shapely.geometry.polygon import Polygon
from shapely.ops import unary_union

import rightmove.models
from flathunt.geometry import poly_bng_to_wgs84
from flathunt.cache import ModelCache
from flathunt.filters import (
    fetch_properties_within_optimal_regions,
    filter_properties_by_budget_and_features,
)

logger = logging.getLogger(__name__)


class Config(dg.Config):
    channel: Literal["RENT", "BUY"] = "BUY"
    # For BUY: purchase price in £. For RENT: monthly rent in £.
    min_budget: float = 100_000
    max_budget: float = 2_000_000
    has_floorplans: bool = False
    has_images: bool = False
    min_square_meters: float = 0.0
    cache_data_dir: str = "cache"


@dg.asset
def candidate_properties(
    config: Config,
    isochrone_intersection: list[Polygon],
) -> list[rightmove.models.MapProperty]:
    """Fetch and filter Rightmove properties within the isochrone intersection area.

    Tiles the bounding box of the intersection polygons, queries Rightmove for
    all properties within each tile, then filters by budget, floor area, images,
    and floorplan availability.  Results are cached in a SQLite database to
    avoid redundant API calls on subsequent runs.

    Args:
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
    cache: ModelCache[list[rightmove.models.MapProperty]] = ModelCache(
        list[rightmove.models.MapProperty], cache_path
    )

    logger.info(
        "Fetching %s properties within %d intersection polygon(s).",
        config.channel,
        len(non_empty),
    )
    properties = fetch_properties_within_optimal_regions(
        non_empty,
        config.channel,
        bounding_polygon,
        cache,
    )
    logger.info(
        "Retrieved %d propert(ies) before budget/feature filtering.", len(properties)
    )

    filtered = filter_properties_by_budget_and_features(
        properties,
        config.min_budget,
        config.max_budget,
        config.has_floorplans,
        config.has_images,
        config.min_square_meters,
        config.channel,
    )
    logger.info("%d propert(ies) remain after budget/feature filtering.", len(filtered))
    return filtered
