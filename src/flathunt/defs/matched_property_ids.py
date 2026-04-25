import asyncio
import logging
from pathlib import Path

import dagster as dg

import rightmove.models
from flathunt.cache import ModelCache
from flathunt.coords import CommuteDest
from flathunt.defs.resources import CacheResource, QueriesResource, TflResource
from flathunt.filters import filter_by_commute
from flathunt.models import MatchedProperty
from flathunt.property_search import (
    DEFAULT_JOURNEY_CACHE_TTL,
    get_properties_journey_duration_cached,
)

logger = logging.getLogger(__name__)


def _build_commute_destinations(queries: QueriesResource) -> list[CommuteDest]:
    return [
        CommuteDest(lon=q.lon, lat=q.lat, max_duration=q.max_duration)
        for q in queries.queries
    ]


@dg.asset(group_name="property_search")
def matched_property_ids(
    context: dg.AssetExecutionContext,
    queries: QueriesResource,
    tfl_resource: TflResource,
    cache: CacheResource,
    candidate_properties: list[rightmove.models.MapProperty],
) -> list[MatchedProperty]:
    """Filter candidate properties by real TfL commute times and return matching IDs with durations.

    Journey durations from each property to every configured destination are
    fetched via the TfL Journey Planner API (cached in SQLite for 7 days).
    Only properties where *every* commute is within the corresponding
    ``max_duration`` are included in the output.

    Args:
        context: Dagster asset execution context, used for progress logging.
        queries: Commute destinations with time limits.
        tfl_resource: TfL API resource providing the API key.
        cache: Cache resource providing the cache directory path.
        candidate_properties: Properties pre-filtered by area and basic
            constraints, as produced by the ``candidate_properties`` asset.

    Returns:
        A list of :class:`MatchedProperty` values pairing each passing property
        ID with its per-destination commute durations in minutes.
    """
    if not candidate_properties:
        logger.info("No candidate properties to evaluate.")
        return []

    dests = _build_commute_destinations(queries)

    cache_path = Path(cache.data_dir) / "journey_cache.db"
    logger.info("Opening journey cache at %s.", cache_path)
    journey_cache: ModelCache[int | None] = ModelCache(
        int | None, cache_path, ttl=DEFAULT_JOURNEY_CACHE_TTL
    )

    flat_to_froms = [
        (prop.location.longitude, prop.location.latitude, d.lon, d.lat)
        for prop in candidate_properties
        for d in dests
    ]
    total = len(flat_to_froms)
    logger.info(
        "Fetching TfL commute durations for %d propert(ies) x %d destination(s).",
        len(candidate_properties),
        len(dests),
    )

    async def _run_all() -> list[list[int | None]]:
        results: list[int | None] = [None] * total
        received = 0
        async for idx, duration in get_properties_journey_duration_cached(
            flat_to_froms, journey_cache, tfl_resource.api_key
        ):
            results[idx] = duration
            received += 1
            if received % 10 == 0 or received == total:
                context.log.info("Journey results received: %d / %d.", received, total)
        n = len(dests)
        return [results[i * n : (i + 1) * n] for i in range(len(candidate_properties))]

    durations = asyncio.run(_run_all())

    matched = filter_by_commute(candidate_properties, durations, dests)
    result = [
        MatchedProperty(property_id=prop.id, commute_durations=list(durs))
        for prop, durs in matched
    ]
    logger.info(
        "%d / %d propert(ies) matched all commute constraints.",
        len(result),
        len(candidate_properties),
    )
    return result
