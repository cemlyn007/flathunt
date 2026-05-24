import asyncio
import logging
from collections.abc import Iterator
from pathlib import Path

import dagster as dg

from flathunt.cache import ModelCache
from flathunt.coords import CommuteDest
from flathunt.defs.resources import CacheResource, QueriesResource, TflResource
from flathunt.models import MatchedProperty
from flathunt.property_search import (
    DEFAULT_JOURNEY_CACHE_TTL,
    get_properties_journey_duration_cached,
)
from zoopla.models import ZooplaListingDetail

logger = logging.getLogger(__name__)


@dg.asset(group_name="zoopla", output_required=False)
def zoopla_matched_ids(
    context: dg.AssetExecutionContext,
    queries: QueriesResource,
    tfl_resource: TflResource,
    cache: CacheResource,
    zoopla_candidate_properties: list[ZooplaListingDetail],
) -> Iterator[dg.Output[list[MatchedProperty]] | dg.AssetObservation]:
    """Filter candidate Zoopla listings by TfL commute times.

    Mirrors ``matched_property_ids`` in the Rightmove pipeline.  Only listings
    where every configured commute is within its maximum duration are returned.

    Args:
        context: Dagster execution context.
        queries: Commute destinations with time limits.
        tfl_resource: TfL API resource providing the API key.
        cache: Cache resource providing the cache directory path.
        zoopla_candidate_properties: Listings that passed all cheap filters.

    Returns:
        Listings where every commute is within its configured maximum, paired
        with per-destination durations in minutes.
    """
    if not zoopla_candidate_properties:
        logger.info("No candidate Zoopla properties to evaluate.")
        yield dg.AssetObservation(
            asset_key=context.asset_key,
            metadata={"candidate_count": 0, "matched_count": 0},
        )
        return

    dests = [
        CommuteDest(lon=q.lon, lat=q.lat, max_duration=q.max_duration)
        for q in queries.queries
    ]
    if not dests:
        context.log.warning(
            "No commute destinations configured; returning all candidate listings."
        )
        result = [
            MatchedProperty(property_id=int(d.listing_id), commute_durations=[])
            for d in zoopla_candidate_properties
        ]
        yield dg.Output(
            result,
            metadata={
                "candidate_count": len(zoopla_candidate_properties),
                "matched_count": len(result),
            },
        )
        return

    # Split candidates: listings without coordinates skip TfL lookup and are kept
    # as commute-unknown; listings with coordinates are evaluated against dests.
    with_coords = [
        d
        for d in zoopla_candidate_properties
        if d.latitude is not None and d.longitude is not None
    ]
    without_coords = [
        d
        for d in zoopla_candidate_properties
        if d.latitude is None or d.longitude is None
    ]

    for detail in without_coords:
        context.log.info(
            "Listing %s has no coordinates; keeping as commute-unknown.",
            detail.listing_id,
        )

    flat_to_froms: list[tuple[float, float, float, float]] = [
        (detail.longitude, detail.latitude, dest.lon, dest.lat)
        for detail in with_coords
        for dest in dests
        if detail.longitude is not None and detail.latitude is not None
    ]
    total = len(flat_to_froms)
    context.log.info(
        "Fetching TfL commute durations for %d listing(s) x %d destination(s).",
        len(with_coords),
        len(dests),
    )

    cache_path = Path(cache.data_dir) / "journey_cache.db"
    journey_cache: ModelCache[int | None] = ModelCache(
        int | None, cache_path, ttl=DEFAULT_JOURNEY_CACHE_TTL
    )

    async def _run_all() -> list[list[int | None]]:
        results: list[int | None] = [None] * total
        received = 0
        async for idx, duration in get_properties_journey_duration_cached(
            flat_to_froms, journey_cache, tfl_resource.api_key
        ):
            results[idx] = duration
            received += 1
            if received % 5 == 0 or received == total:
                context.log.info("Journey results: %d / %d.", received, total)
        n = len(dests)
        return [results[i * n : (i + 1) * n] for i in range(len(with_coords))]

    all_durations = asyncio.run(_run_all())

    matched: list[MatchedProperty] = []
    # Commute-unknown listings always pass (null-safe: unknown duration ≠ failure).
    matched.extend(
        MatchedProperty(property_id=int(d.listing_id), commute_durations=[])
        for d in without_coords
    )
    # Listings with coordinates: reject only if a known duration exceeds its max.
    # A None duration (lookup failed) is treated as unknown → KEEP.
    for detail, prop_durations in zip(with_coords, all_durations, strict=True):
        if any(
            d is not None and d > dest.max_duration
            for d, dest in zip(prop_durations, dests, strict=True)
        ):
            context.log.info(
                "Listing %s failed commute filter (durations=%s).",
                detail.listing_id,
                prop_durations,
            )
        else:
            matched.append(
                MatchedProperty(
                    property_id=int(detail.listing_id),
                    commute_durations=list(prop_durations),
                )
            )

    context.log.info(
        "%d / %d listing(s) passed commute filter.",
        len(matched),
        len(zoopla_candidate_properties),
    )
    metadata = {
        "candidate_count": len(zoopla_candidate_properties),
        "matched_count": len(matched),
    }
    if not matched:
        yield dg.AssetObservation(asset_key=context.asset_key, metadata=metadata)
        return
    yield dg.Output(matched, metadata=metadata)
