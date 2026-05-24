import asyncio
import logging
from collections.abc import Iterator
from pathlib import Path

import dagster as dg

from flathunt.cache import ModelCache
from flathunt.coords import CommuteDest
from flathunt.defs.resources import CacheResource, QueriesResource, TflResource
from flathunt.models import FinalProperty, MatchedProperty
from flathunt.property_search import (
    DEFAULT_JOURNEY_CACHE_TTL,
    get_properties_journey_duration_cached,
)

logger = logging.getLogger(__name__)

__all__ = ["rightmove_email_matched_ids"]


@dg.asset(group_name="rightmove_email", output_required=False)
def rightmove_email_matched_ids(
    context: dg.AssetExecutionContext,
    queries: QueriesResource,
    tfl_resource: TflResource,
    cache: CacheResource,
    rightmove_email_candidate_properties: list[FinalProperty],
) -> Iterator[dg.Output[list[MatchedProperty]] | dg.AssetObservation]:
    """Filter candidate Rightmove email listings by TfL commute times.

    Mirrors ``zoopla_matched_ids``.  Only listings where every configured
    commute is within its maximum duration are returned.  Listings without
    coordinates are kept as commute-unknown (``commute_durations=[]``).

    Args:
        context: Dagster execution context.
        queries: Commute destinations with time limits.
        tfl_resource: TfL API resource providing the API key.
        cache: Cache resource providing the cache directory path.
        rightmove_email_candidate_properties: Listings that passed all cheap filters.

    Returns:
        Listings where every commute is within its configured maximum, paired
        with per-destination durations in minutes.
    """
    if not rightmove_email_candidate_properties:
        logger.info("No candidate Rightmove email properties to evaluate.")
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
            MatchedProperty(property_id=prop.id, commute_durations=[])
            for prop in rightmove_email_candidate_properties
        ]
        yield dg.Output(
            result,
            metadata={
                "candidate_count": len(rightmove_email_candidate_properties),
                "matched_count": len(result),
            },
        )
        return

    # Split candidates: listings without coordinates skip TfL lookup and are kept
    # as commute-unknown; listings with coordinates are evaluated against dests.
    with_coords = [
        prop
        for prop in rightmove_email_candidate_properties
        if prop.latitude is not None and prop.longitude is not None
    ]
    without_coords = [
        prop
        for prop in rightmove_email_candidate_properties
        if prop.latitude is None or prop.longitude is None
    ]

    for prop in without_coords:
        context.log.info(
            "Property %s has no coordinates; keeping as commute-unknown.",
            prop.id,
        )

    flat_to_froms: list[tuple[float, float, float, float]] = []
    for prop in with_coords:
        assert prop.longitude is not None and prop.latitude is not None
        flat_to_froms.extend(
            (prop.longitude, prop.latitude, dest.lon, dest.lat) for dest in dests
        )
    total = len(flat_to_froms)
    context.log.info(
        "Fetching TfL commute durations for %d property(-ies) x %d destination(s).",
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
    # Commute-unknown listings always pass (null-safe: unknown duration != failure).
    matched.extend(
        MatchedProperty(property_id=prop.id, commute_durations=[])
        for prop in without_coords
    )
    # Listings with coordinates: reject only if a known duration exceeds its max.
    # A None duration (lookup failed) is treated as unknown → KEEP.
    for prop, prop_durations in zip(with_coords, all_durations, strict=True):
        if any(
            d is not None and d > dest.max_duration
            for d, dest in zip(prop_durations, dests, strict=True)
        ):
            context.log.info(
                "Property %s failed commute filter (durations=%s).",
                prop.id,
                prop_durations,
            )
        else:
            matched.append(
                MatchedProperty(
                    property_id=prop.id,
                    commute_durations=list(prop_durations),
                )
            )

    context.log.info(
        "%d / %d property(-ies) passed commute filter.",
        len(matched),
        len(rightmove_email_candidate_properties),
    )
    metadata = {
        "candidate_count": len(rightmove_email_candidate_properties),
        "matched_count": len(matched),
    }
    if not matched:
        yield dg.AssetObservation(asset_key=context.asset_key, metadata=metadata)
        return
    yield dg.Output(matched, metadata=metadata)
