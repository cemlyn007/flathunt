import asyncio
import logging
from pathlib import Path

import dagster as dg

import rightmove.api
import rightmove.models
from flathunt.cache import ModelCache
from flathunt.defs.resources import CacheResource
from flathunt.floor_plan_batch import get_floor_plan_sqm
from flathunt.models import FinalProperty
from rightmove.email_models import RightmoveProperty, RightmovePropertyAlert
from rightmove.floor_plan import FloorPlanSizeExtractor

logger = logging.getLogger(__name__)

__all__ = ["rightmove_enriched_properties"]

_DETAIL_CACHE_TTL = 7 * 24 * 3600  # 7 days
_DETAILS_CONCURRENCY = 3
_FLOOR_PLAN_CACHE_TTL = 30 * 24 * 3600  # 30 days
_LLM_CONCURRENCY = 1


def _to_final_property(
    prop_listing_id: str,
    prop_address: str | None,
    prop_price_gbp: int | None,
    details: rightmove.models.PropertyDetails | None,
    extracted_sqm: float | None = None,
) -> FinalProperty:
    price: rightmove.models.Price | None = None
    if prop_price_gbp is not None:
        price = rightmove.models.Price(amount=prop_price_gbp, frequency="static")

    bedrooms: int | None = None
    bathrooms: int | None = None
    display_size: str | None = None

    council_tax_band: str | None = None
    annual_ground_rent: float | None = None
    ground_rent_review_period_in_years: int | None = None
    ground_rent_percentage_increase: float | None = None
    annual_service_charge: float | None = None
    tenure_type: str | None = None
    years_remaining_on_lease: int | None = None

    latitude: float | None = None
    longitude: float | None = None

    if details is not None:
        bedrooms = details.bedrooms
        bathrooms = details.bathrooms
        if details.size_sqm is not None:
            display_size = f"{details.size_sqm:.0f} sqm"
        lc = details.living_costs
        council_tax_band = lc.council_tax_band
        annual_ground_rent = lc.annual_ground_rent
        ground_rent_review_period_in_years = lc.ground_rent_review_period_in_years
        ground_rent_percentage_increase = lc.ground_rent_percentage_increase
        annual_service_charge = lc.annual_service_charge
        tenure_type = details.tenure_type
        years_remaining_on_lease = details.years_remaining_on_lease
        if details.location is not None:
            latitude = details.location.latitude
            longitude = details.location.longitude

    return FinalProperty(
        id=int(prop_listing_id),
        source="rightmove",
        display_address=prop_address or "",
        property_url=f"/properties/{prop_listing_id}",
        price=price,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        display_size=display_size,
        extracted_sqm=extracted_sqm,
        council_tax_band=council_tax_band,
        annual_ground_rent=annual_ground_rent,
        ground_rent_review_period_in_years=ground_rent_review_period_in_years,
        ground_rent_percentage_increase=ground_rent_percentage_increase,
        annual_service_charge=annual_service_charge,
        tenure_type=tenure_type,
        years_remaining_on_lease=years_remaining_on_lease,
        latitude=latitude,
        longitude=longitude,
    )


async def _extract_sizes(
    properties: list[RightmoveProperty],
    details_by_id: dict[str, rightmove.models.PropertyDetails | None],
    floor_plan_cache: ModelCache[tuple[float | None, str | None]],
    extractor: FloorPlanSizeExtractor,
    llm_semaphore: asyncio.Semaphore,
) -> tuple[dict[str, float | None], dict[str, int]]:
    """Return per-listing fallback ``extracted_sqm`` plus size-source counts.

    Size precedence per listing:
    - Detail page reports a sqm size -> no extraction; ``extracted_sqm`` is None
      (the API ``display_size`` is used downstream). Counted as ``size_from_api``.
    - No API size but the listing has floor plans -> fall back to the (cached)
      floor-plan LLM extraction. Counted as ``size_from_floorplan`` when a value
      is produced, else ``size_missing``.
    - Neither -> ``extracted_sqm`` is None, counted as ``size_missing``.
    """
    extracted: dict[str, float | None] = {}
    counts = {"size_from_api": 0, "size_from_floorplan": 0, "size_missing": 0}

    for prop in properties:
        details = details_by_id.get(prop.listing_id)

        if details is not None and details.size_sqm is not None:
            extracted[prop.listing_id] = None
            counts["size_from_api"] += 1
            continue

        if details is not None and details.floorplans:
            total_sqm, _ = await get_floor_plan_sqm(
                int(prop.listing_id),
                details,
                floor_plan_cache,
                extractor,
                llm_semaphore,
            )
            extracted[prop.listing_id] = total_sqm
            if total_sqm is not None:
                counts["size_from_floorplan"] += 1
            else:
                counts["size_missing"] += 1
            continue

        extracted[prop.listing_id] = None
        counts["size_missing"] += 1

    return extracted, counts


@dg.asset(group_name="rightmove_email")
def rightmove_enriched_properties(
    context: dg.AssetExecutionContext,
    cache: CacheResource,
    rightmove_property_alerts: list[RightmovePropertyAlert],
) -> list[FinalProperty]:
    deduped_props: dict[str, RightmoveProperty] = {}
    for alert in rightmove_property_alerts:
        for prop in alert.properties:
            deduped_props.setdefault(prop.listing_id, prop)
    properties = list(deduped_props.values())

    if not properties:
        context.log.info("No properties across alerts; skipping detail fetch.")
        context.add_output_metadata({
            "alert_count": len(rightmove_property_alerts),
            "total_count": 0,
            "cache_hit_count": 0,
            "fetched_count": 0,
            "failed_count": 0,
        })
        return []

    cache_path = Path(cache.data_dir) / "rightmove_email_detail_cache.db"
    detail_cache: ModelCache[rightmove.models.PropertyDetails] = ModelCache(
        rightmove.models.PropertyDetails,
        cache_path,
        ttl=_DETAIL_CACHE_TTL,
    )

    client = rightmove.api.Rightmove()

    async def _fetch_all() -> dict[str, rightmove.models.PropertyDetails | None]:
        semaphore = asyncio.Semaphore(_DETAILS_CONCURRENCY)
        results: dict[str, rightmove.models.PropertyDetails | None] = {}
        cache_hit_count = 0
        fetched_count = 0
        failed_count = 0

        for prop in properties:
            try:
                details = detail_cache.get(prop.listing_id)
                results[prop.listing_id] = details
                cache_hit_count += 1
                context.log.info("Cache hit for listing %s.", prop.listing_id)
            except KeyError:
                try:
                    async with semaphore:
                        details = await client.get_property_details(
                            f"/properties/{prop.listing_id}"
                        )
                    detail_cache.update([(prop.listing_id, details)])
                    results[prop.listing_id] = details
                    fetched_count += 1
                    context.log.info("Fetched details for listing %s.", prop.listing_id)
                except Exception:
                    logger.exception(
                        "Failed to fetch details for listing %s.", prop.listing_id
                    )
                    results[prop.listing_id] = None
                    failed_count += 1

        context.add_output_metadata({
            "alert_count": len(rightmove_property_alerts),
            "total_count": len(properties),
            "cache_hit_count": cache_hit_count,
            "fetched_count": fetched_count,
            "failed_count": failed_count,
        })
        return results

    details_by_id = asyncio.run(_fetch_all())

    floor_plan_cache_path = Path(cache.data_dir) / "floor_plan_size_cache.db"
    floor_plan_cache: ModelCache[tuple[float | None, str | None]] = ModelCache(
        tuple[float | None, str | None],
        floor_plan_cache_path,
        ttl=_FLOOR_PLAN_CACHE_TTL,
    )
    extractor = FloorPlanSizeExtractor()

    async def _run_sizes() -> tuple[dict[str, float | None], dict[str, int]]:
        llm_semaphore = asyncio.Semaphore(_LLM_CONCURRENCY)
        return await _extract_sizes(
            properties, details_by_id, floor_plan_cache, extractor, llm_semaphore
        )

    extracted_sqm_by_id, size_counts = asyncio.run(_run_sizes())
    context.add_output_metadata(size_counts)

    final_properties = [
        _to_final_property(
            prop.listing_id,
            prop.address,
            prop.price_gbp,
            details_by_id.get(prop.listing_id),
            extracted_sqm_by_id.get(prop.listing_id),
        )
        for prop in properties
    ]
    context.log.info(
        "Returning %d enriched Rightmove listing(s).", len(final_properties)
    )
    return final_properties
