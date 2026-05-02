import asyncio
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import dagster as dg
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon

from flathunt.cache import ModelCache
from flathunt.coords import CommuteDest
from flathunt.defs.resources import CacheResource, QueriesResource, TflResource
from flathunt.geometry import wgs84_to_bng
from flathunt.models import FinalProperty
from flathunt.property_search import (
    DEFAULT_JOURNEY_CACHE_TTL,
    get_properties_journey_duration_cached,
)
from rightmove.email_models import RightmoveProperty, RightmovePropertyAlert

logger = logging.getLogger(__name__)

__all__ = ["rightmove_email_matched_properties"]

_EMAIL_MATCHES_DB = "rightmove_email_matches.db"


def _open_matches_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS email_matches ("
        "  property_id TEXT PRIMARY KEY,"
        "  found_at INTEGER NOT NULL"
        ")"
    )
    conn.commit()
    return conn


def _record_matched_ids(path: Path, ids: list[str]) -> None:
    now = int(datetime.now(tz=UTC).timestamp())
    with _open_matches_db(path) as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO email_matches (property_id, found_at) VALUES (?, ?)",
            [(pid, now) for pid in ids],
        )


class Config(dg.Config):
    min_budget: float
    max_budget: float
    has_floorplans: bool
    has_images: bool
    min_square_meters: float


@dg.asset(group_name="rightmove")
def rightmove_email_matched_properties(
    context: dg.AssetExecutionContext,
    config: Config,
    cache: CacheResource,
    tfl_resource: TflResource,
    queries: QueriesResource,
    isochrone_intersection: list[Polygon],
    rightmove_property_alerts: list[RightmovePropertyAlert],
    rightmove_enriched_properties: list[FinalProperty],
) -> list[FinalProperty]:
    if not rightmove_enriched_properties:
        context.log.info("No enriched Rightmove properties; returning empty list.")
        context.add_output_metadata({"total_count": 0, "matched_count": 0})
        return []

    email_by_id: dict[str, RightmoveProperty] = {}
    for alert in rightmove_property_alerts:
        for prop in alert.properties:
            email_by_id.setdefault(prop.listing_id, prop)

    total = len(rightmove_enriched_properties)
    after_price = after_floorplans = after_photos = after_isochrone = 0
    no_coords_excluded = 0

    # Filter 1: price
    price_passed: list[FinalProperty] = []
    for prop in rightmove_enriched_properties:
        amount = prop.price.amount if prop.price else None
        if amount is None:
            context.log.info("Property %s has no price; excluding.", prop.id)
            continue
        if config.min_budget <= amount <= config.max_budget:
            price_passed.append(prop)
        else:
            context.log.info(
                "Property %s price £%d outside [%d, %d]; excluding.",
                prop.id,
                amount,
                config.min_budget,
                config.max_budget,
            )
    after_price = len(price_passed)

    # Filter 2: floorplans
    floorplan_passed: list[FinalProperty] = []
    for prop in price_passed:
        if config.has_floorplans:
            ep = email_by_id.get(str(prop.id))
            count = ep.floorplan_count if ep is not None else None
            if count is None or count == 0:
                context.log.info(
                    "Property %s has no floorplans (count=%s); excluding.",
                    prop.id,
                    count,
                )
                continue
        floorplan_passed.append(prop)
    after_floorplans = len(floorplan_passed)

    # Filter 3: photos
    photo_passed: list[FinalProperty] = []
    for prop in floorplan_passed:
        if config.has_images:
            ep = email_by_id.get(str(prop.id))
            count = ep.photo_count if ep is not None else None
            if count is None or count <= 2:
                context.log.info(
                    "Property %s has insufficient photos (count=%s); excluding.",
                    prop.id,
                    count,
                )
                continue
        photo_passed.append(prop)
    after_photos = len(photo_passed)

    # Filter 4: isochrone (geographic)
    isochrone_passed: list[FinalProperty] = []
    for prop in photo_passed:
        if prop.latitude is None or prop.longitude is None:
            context.log.warning(
                "Property %s has no coordinates; excluding from email pipeline.",
                prop.id,
            )
            no_coords_excluded += 1
            continue
        easting, northing = wgs84_to_bng(prop.longitude, prop.latitude)
        pt = Point(easting, northing)
        if isochrone_intersection and any(
            poly.contains(pt) for poly in isochrone_intersection
        ):
            isochrone_passed.append(prop)
        else:
            context.log.info(
                "Property %s at (%.4f, %.4f) outside isochrone; excluding.",
                prop.id,
                prop.latitude,
                prop.longitude,
            )
    after_isochrone = len(isochrone_passed)

    context.log.info(
        "Filters: total=%d price=%d floorplans=%d photos=%d no_coords=%d isochrone=%d",
        total,
        after_price,
        after_floorplans,
        after_photos,
        no_coords_excluded,
        after_isochrone,
    )

    if not isochrone_passed:
        context.add_output_metadata({
            "total_count": total,
            "after_price": after_price,
            "after_floorplans": after_floorplans,
            "after_photos": after_photos,
            "no_coords_excluded": no_coords_excluded,
            "after_isochrone": after_isochrone,
            "matched_count": 0,
        })
        return []

    # Filter 5: TfL commute
    dests = [
        CommuteDest(lon=q.lon, lat=q.lat, max_duration=q.max_duration)
        for q in queries.queries
    ]

    if not dests:
        context.log.warning(
            "No commute destinations configured; keeping all isochrone-passed properties."
        )
        matched = [
            prop.model_copy(update={"commute_durations": []})
            for prop in isochrone_passed
        ]
    else:
        flat_to_froms: list[tuple[float, float, float, float]] = [
            (prop.longitude, prop.latitude, dest.lon, dest.lat)
            for prop in isochrone_passed
            for dest in dests
            if prop.longitude is not None and prop.latitude is not None
        ]
        total_pairs = len(flat_to_froms)

        cache_path = Path(cache.data_dir) / "journey_cache.db"
        journey_cache: ModelCache[int | None] = ModelCache(
            int | None, cache_path, ttl=DEFAULT_JOURNEY_CACHE_TTL
        )

        async def _run_all() -> list[list[int | None]]:
            raw: list[int | None] = [None] * total_pairs
            received = 0
            async for idx, duration in get_properties_journey_duration_cached(
                flat_to_froms, journey_cache, tfl_resource.api_key
            ):
                raw[idx] = duration
                received += 1
                if received % 5 == 0 or received == total_pairs:
                    context.log.info("Journey results: %d / %d.", received, total_pairs)
            n = len(dests)
            return [raw[i * n : (i + 1) * n] for i in range(len(isochrone_passed))]

        all_durations = asyncio.run(_run_all())

        matched: list[FinalProperty] = []
        for prop, durations in zip(isochrone_passed, all_durations, strict=False):
            if all(
                d is not None and d <= dest.max_duration
                for d, dest in zip(durations, dests, strict=False)
            ):
                matched.append(
                    prop.model_copy(update={"commute_durations": list(durations)})
                )
            else:
                context.log.info(
                    "Property %s failed commute filter (durations=%s).",
                    prop.id,
                    durations,
                )

    # Filter 6: floor area (only when extracted_sqm is available; currently always None
    # for email-pipeline properties, so all pass — consistent with search pipeline behaviour
    # for properties with unknown size)
    size_passed = [
        p
        for p in matched
        if p.extracted_sqm is None or p.extracted_sqm >= config.min_square_meters
    ]

    context.log.info(
        "%d / %d email properties passed all filters.",
        len(size_passed),
        total,
    )

    # Record matched IDs for pipeline comparison
    db_path = Path(cache.data_dir) / _EMAIL_MATCHES_DB
    _record_matched_ids(db_path, [str(p.id) for p in size_passed])

    context.add_output_metadata({
        "total_count": total,
        "after_price": after_price,
        "after_floorplans": after_floorplans,
        "after_photos": after_photos,
        "no_coords_excluded": no_coords_excluded,
        "after_isochrone": after_isochrone,
        "matched_count": len(size_passed),
    })
    return size_passed
