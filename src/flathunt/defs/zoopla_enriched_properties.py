import asyncio
import logging
from pathlib import Path

import dagster as dg

from flathunt.cache import ModelCache
from flathunt.defs.resources import CacheResource
from flathunt.property_search import DEFAULT_JOURNEY_CACHE_TTL
from zoopla.client import ZooplaClient
from zoopla.models import ZooplaListingDetail, ZooplaProperty, ZooplaPropertyAlert

logger = logging.getLogger(__name__)

__all__ = ["zoopla_enriched_properties"]

_DETAIL_CACHE_TTL = DEFAULT_JOURNEY_CACHE_TTL


def _looks_unparsed(detail: ZooplaListingDetail) -> bool:
    # Pages served behind a bot wall or that fail to settle yield a detail with
    # no address and no coordinates. Treat these as transient parse failures.
    return (
        detail.latitude is None and detail.longitude is None and detail.address is None
    )


@dg.asset(group_name="zoopla")
def zoopla_enriched_properties(
    context: dg.AssetExecutionContext,
    cache: CacheResource,
    zoopla_property_alerts: list[ZooplaPropertyAlert],
) -> list[ZooplaListingDetail]:
    deduped_props: dict[str, ZooplaProperty] = {}
    for alert in zoopla_property_alerts:
        for prop in alert.properties:
            deduped_props.setdefault(prop.listing_id, prop)
    properties = list(deduped_props.values())

    if not properties:
        context.log.info("No properties across alerts; skipping detail fetch.")
        return []

    cache_path = Path(cache.data_dir) / "zoopla_detail_cache.db"
    detail_cache: ModelCache[ZooplaListingDetail] = ModelCache(
        ZooplaListingDetail, cache_path, ttl=_DETAIL_CACHE_TTL
    )

    to_fetch = []
    results: dict[str, ZooplaListingDetail] = {}

    for prop in properties:
        try:
            cached = detail_cache.get(prop.listing_id)
        except KeyError:
            to_fetch.append(prop)
            continue
        if _looks_unparsed(cached):
            context.log.warning(
                "Cached detail for listing %s looks unparsed; refetching.",
                prop.listing_id,
            )
            to_fetch.append(prop)
        else:
            results[prop.listing_id] = cached
            context.log.info("Cache hit for listing %s.", prop.listing_id)

    if to_fetch:
        context.log.info(
            "Fetching details for %d listing(s) via Playwright.", len(to_fetch)
        )

        async def _fetch_all() -> list[ZooplaListingDetail]:
            fetched: list[ZooplaListingDetail] = []
            async with ZooplaClient() as client:
                for prop in to_fetch:
                    context.log.info("Fetching %s", prop.url)
                    detail = await client.get_listing_detail(prop.url)
                    fetched.append(detail)
            return fetched

        fetched_details = asyncio.run(_fetch_all())
        cacheable = [d for d in fetched_details if not _looks_unparsed(d)]
        unparsed = len(fetched_details) - len(cacheable)
        if unparsed:
            context.log.warning(
                "Skipping cache for %d listing(s) that returned no address or coordinates.",
                unparsed,
            )
        detail_cache.update((d.listing_id, d) for d in cacheable)
        for detail in fetched_details:
            results[detail.listing_id] = detail

    ordered = [results[p.listing_id] for p in properties if p.listing_id in results]
    context.log.info("Returning %d enriched Zoopla listing(s).", len(ordered))
    context.add_output_metadata({
        "alert_count": len(zoopla_property_alerts),
        "total_count": len(ordered),
        "cache_hit_count": len(results) - len(to_fetch),
        "fetched_count": len(to_fetch),
    })
    return ordered
