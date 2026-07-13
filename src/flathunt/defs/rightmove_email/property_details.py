import asyncio
import logging
from pathlib import Path

import dagster as dg
import httpx

import rightmove.api
import rightmove.models
from flathunt.cache import ModelCache
from flathunt.defs.resources import CacheResource
from rightmove.email_models import RightmovePropertyAlert

__all__ = ["rightmove_email_property_details"]

_DELISTED_STATUS_CODES = frozenset({404, 410})

logger = logging.getLogger(__name__)

_DETAIL_CACHE_TTL = 7 * 24 * 3600  # 7 days
_DETAILS_CONCURRENCY = 3


@dg.asset(group_name="rightmove_email", io_manager_key="fs_io_manager")
async def rightmove_email_property_details(
    context: dg.AssetExecutionContext,
    cache: CacheResource,
    rightmove_property_alerts: list[RightmovePropertyAlert],
) -> dict[str, rightmove.models.PropertyDetailsFetchResult]:
    deduped: dict[str, str] = {}
    for alert in rightmove_property_alerts:
        for prop in alert.properties:
            deduped.setdefault(prop.listing_id, prop.listing_id)
    listing_ids = list(deduped.keys())

    if not listing_ids:
        context.log.info("No properties across alerts; skipping detail fetch.")
        context.add_output_metadata({
            "alert_count": len(rightmove_property_alerts),
            "total_count": 0,
            "cache_hit_count": 0,
            "fetched_count": 0,
            "failed_count": 0,
            "delisted_count": 0,
        })
        return {}

    cache_path = Path(cache.data_dir) / "rightmove_email_detail_cache.db"
    detail_cache: ModelCache[rightmove.models.PropertyDetails] = ModelCache(
        rightmove.models.PropertyDetails,
        cache_path,
        ttl=_DETAIL_CACHE_TTL,
    )

    client = rightmove.api.Rightmove()
    semaphore = asyncio.Semaphore(_DETAILS_CONCURRENCY)
    results: dict[str, rightmove.models.PropertyDetailsFetchResult] = {}
    cache_hit_count = 0
    fetched_count = 0
    failed_count = 0
    delisted_count = 0

    for listing_id in listing_ids:
        try:
            details = detail_cache.get(listing_id)
            results[listing_id] = rightmove.models.PropertyDetailsFetchResult(
                details=details
            )
            cache_hit_count += 1
            context.log.info("Cache hit for listing %s.", listing_id)
        except KeyError:
            try:
                async with semaphore:
                    details = await client.get_property_details(
                        f"/properties/{listing_id}"
                    )
                detail_cache.update([(listing_id, details)])
                results[listing_id] = rightmove.models.PropertyDetailsFetchResult(
                    details=details
                )
                fetched_count += 1
                context.log.info("Fetched details for listing %s.", listing_id)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in _DELISTED_STATUS_CODES:
                    context.log.info(
                        "Listing %s confirmed delisted by Rightmove (status=%d).",
                        listing_id,
                        exc.response.status_code,
                    )
                    results[listing_id] = rightmove.models.PropertyDetailsFetchResult(
                        is_delisted=True
                    )
                    delisted_count += 1
                else:
                    logger.exception(
                        "Failed to fetch details for listing %s.", listing_id
                    )
                    results[listing_id] = rightmove.models.PropertyDetailsFetchResult()
                    failed_count += 1
            except Exception:
                logger.exception("Failed to fetch details for listing %s.", listing_id)
                results[listing_id] = rightmove.models.PropertyDetailsFetchResult()
                failed_count += 1

    context.add_output_metadata({
        "alert_count": len(rightmove_property_alerts),
        "total_count": len(listing_ids),
        "cache_hit_count": cache_hit_count,
        "fetched_count": fetched_count,
        "failed_count": failed_count,
        "delisted_count": delisted_count,
    })
    return results
