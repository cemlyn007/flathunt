import asyncio
import logging
from pathlib import Path

import dagster as dg

import rightmove.api
import rightmove.models
from flathunt.cache import ModelCache
from flathunt.defs.resources import CacheResource
from flathunt.models import FinalProperty
from rightmove.email_models import RightmovePropertyAlert

logger = logging.getLogger(__name__)

__all__ = ["rightmove_enriched_properties"]

_DETAIL_CACHE_TTL = 7 * 24 * 3600  # 7 days
_DETAILS_CONCURRENCY = 3


def _to_final_property(
    prop_listing_id: str,
    prop_address: str | None,
    prop_price_gbp: int | None,
    details: rightmove.models.PropertyDetails | None,
) -> FinalProperty:
    price: rightmove.models.Price | None = None
    if prop_price_gbp is not None:
        price = rightmove.models.Price(amount=prop_price_gbp, frequency="static")

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


@dg.asset(group_name="rightmove")
def rightmove_enriched_properties(
    context: dg.AssetExecutionContext,
    cache: CacheResource,
    rightmove_property_alerts: RightmovePropertyAlert,
) -> list[FinalProperty]:
    if not rightmove_property_alerts.properties:
        context.log.info("No properties in alert; skipping detail fetch.")
        context.add_output_metadata({
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

        for prop in rightmove_property_alerts.properties:
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
            "total_count": len(rightmove_property_alerts.properties),
            "cache_hit_count": cache_hit_count,
            "fetched_count": fetched_count,
            "failed_count": failed_count,
        })
        return results

    details_by_id = asyncio.run(_fetch_all())

    final_properties = [
        _to_final_property(
            prop.listing_id,
            prop.address,
            prop.price_gbp,
            details_by_id.get(prop.listing_id),
        )
        for prop in rightmove_property_alerts.properties
    ]
    context.log.info(
        "Returning %d enriched Rightmove listing(s).", len(final_properties)
    )
    return final_properties
