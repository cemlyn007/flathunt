import asyncio
import logging
from pathlib import Path

import dagster as dg

import rightmove.api
import rightmove.models
from flathunt.cache import ModelCache
from flathunt.defs.resources import CacheResource
from flathunt.models import MatchedProperty

logger = logging.getLogger(__name__)

_PROPERTY_DETAILS_CACHE_TTL = 7 * 24 * 3600  # 7 days
_DETAILS_CONCURRENCY = 3


@dg.asset(group_name="rightmove_search")
def rightmove_property_details(
    context: dg.AssetExecutionContext,
    cache: CacheResource,
    matched_property_ids: list[MatchedProperty],
    candidate_properties: list[rightmove.models.MapProperty],
) -> dict[int, rightmove.models.PropertyDetails | None]:
    """Fetch Rightmove property detail pages for all matched properties.

    Results are cached in a SQLite database with a 7-day TTL so that
    re-running the enrichment pipeline does not re-fetch unchanged pages.

    Args:
        context: Dagster asset execution context, used for progress logging.
        cache: CacheResource providing cache directory.
        matched_property_ids: Properties that passed the commute filter.
        candidate_properties: Full property objects from ``candidate_properties``.

    Returns:
        A mapping from property ID to its :class:`rightmove.models.PropertyDetails`,
        or ``None`` when the detail page could not be fetched.
    """
    if not matched_property_ids:
        context.add_output_metadata({
            "total_count": 0,
            "cache_hit_count": 0,
            "fetched_count": 0,
            "failed_count": 0,
        })
        return {}

    matched_set = {m.property_id for m in matched_property_ids}
    props_by_id = {p.id: p for p in candidate_properties if p.id in matched_set}

    details_cache_path = Path(cache.data_dir) / "property_details_cache.db"
    details_cache: ModelCache[rightmove.models.PropertyDetails] = ModelCache(
        rightmove.models.PropertyDetails,
        details_cache_path,
        ttl=_PROPERTY_DETAILS_CACHE_TTL,
    )

    rightmove_client = rightmove.api.Rightmove()

    async def _fetch_all() -> dict[int, rightmove.models.PropertyDetails | None]:
        details_semaphore = asyncio.Semaphore(_DETAILS_CONCURRENCY)
        result: dict[int, rightmove.models.PropertyDetails | None] = {}
        cache_hit_count = 0
        fetched_count = 0
        failed_count = 0

        for matched in matched_property_ids:
            prop = props_by_id.get(matched.property_id)
            if prop is None:
                result[matched.property_id] = None
                continue

            cache_key = str(prop.id)
            try:
                details = details_cache.get(cache_key)
                result[prop.id] = details
                cache_hit_count += 1
                logger.debug("Property details cache hit for property %d.", prop.id)
            except KeyError:
                try:
                    async with details_semaphore:
                        details = await rightmove_client.get_property_details(
                            prop.property_url
                        )
                    details_cache.update([(cache_key, details)])
                    result[prop.id] = details
                    fetched_count += 1
                except Exception:
                    logger.exception(
                        "Failed to fetch property details for property %d.", prop.id
                    )
                    result[prop.id] = None
                    failed_count += 1

        context.add_output_metadata({
            "total_count": len(matched_property_ids),
            "cache_hit_count": cache_hit_count,
            "fetched_count": fetched_count,
            "failed_count": failed_count,
        })
        return result

    return asyncio.run(_fetch_all())
