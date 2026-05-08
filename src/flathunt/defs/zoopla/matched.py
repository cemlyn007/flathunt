import asyncio
import logging
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
from rightmove.floor_plan import _SQFT_TO_SQM
from rightmove.models import Price
from zoopla.models import ZooplaListingDetail

logger = logging.getLogger(__name__)

__all__ = ["zoopla_matched_properties"]


def _to_final_property(
    detail: ZooplaListingDetail,
    commute_durations: list[int | None],
    extractions: dict[str, tuple[float | None, str | None]],
) -> FinalProperty:
    price = None
    if detail.price_gbp is not None:
        price = Price(amount=detail.price_gbp, frequency="monthly")

    display_size = None
    extracted_sqm: float | None = None
    extracted_sqm_breakdown: str | None = None

    if detail.floor_area_sqft is not None:
        # Structured size from Zoopla wins.
        display_size = f"{detail.floor_area_sqft} sq. ft."
        extracted_sqm = float(int(detail.floor_area_sqft * _SQFT_TO_SQM))
    elif detail.listing_id in extractions:
        # Vision-extracted size.
        sqm, breakdown = extractions[detail.listing_id]
        if sqm is not None:
            extracted_sqm = sqm
            display_size = (
                f"{int(sqm)} sqm"  # round-trips through parse_display_size_sqm
            )
        extracted_sqm_breakdown = breakdown

    return FinalProperty(
        id=int(detail.listing_id),
        source="zoopla",
        display_address=detail.address or "",
        property_url=detail.url,
        bedrooms=detail.bedrooms,
        bathrooms=detail.bathrooms,
        display_size=display_size,
        extracted_sqm=extracted_sqm,
        extracted_sqm_breakdown=extracted_sqm_breakdown,
        price=price,
        council_tax_band=detail.council_tax_band,
        tenure_type=detail.tenure,
        commute_durations=commute_durations,
    )


def _apply_size_filter(
    details: list[ZooplaListingDetail],
    extractions: dict[str, tuple[float | None, str | None]],
    min_square_meters: float,
    log: logging.Logger,
) -> list[ZooplaListingDetail]:
    """Filter listings by floor area, consulting extracted sizes as a fallback.

    Listings whose size is genuinely unknown (no structured data, no extraction)
    are kept — consistent with prior behaviour for unknown-size listings.  When
    extraction returned ``(None, None)`` (i.e. extraction was attempted but found
    nothing), the listing is also kept for the same reason.
    """
    passed: list[ZooplaListingDetail] = []
    for detail in details:
        sqm: float | None = None
        if detail.floor_area_sqft is not None:
            sqm = detail.floor_area_sqft * _SQFT_TO_SQM
        elif detail.listing_id in extractions:
            sqm, _ = extractions[detail.listing_id]

        if sqm is None:
            # Genuinely unknown size (no structured data, no extraction). Keep —
            # consistent with prior behaviour for unknown-size listings.
            passed.append(detail)
            continue

        if sqm >= min_square_meters:
            passed.append(detail)
        else:
            log.info(
                "Listing %s floor area %.1f sqm below minimum %.1f; excluding.",
                detail.listing_id,
                sqm,
                min_square_meters,
            )
    return passed


class Config(dg.Config):
    min_budget: float
    max_budget: float
    has_images: bool
    min_square_meters: float


@dg.asset(group_name="zoopla")
def zoopla_matched_properties(
    context: dg.AssetExecutionContext,
    config: Config,
    tfl_resource: TflResource,
    queries: QueriesResource,
    cache: CacheResource,
    zoopla_enriched_properties: list[ZooplaListingDetail],
    zoopla_extracted_floor_plans: dict[str, tuple[float | None, str | None]],
    isochrone_intersection: list[Polygon],
) -> list[FinalProperty]:
    if not zoopla_enriched_properties:
        context.log.info("No enriched Zoopla properties; returning empty list.")
        context.add_output_metadata({"total_count": 0, "matched_count": 0})
        return []

    total_enriched = len(zoopla_enriched_properties)

    # Filter 1: price
    price_passed: list[ZooplaListingDetail] = []
    for detail in zoopla_enriched_properties:
        if detail.price_gbp is None:
            context.log.info("Listing %s has no price; excluding.", detail.listing_id)
            continue
        if config.min_budget <= detail.price_gbp <= config.max_budget:
            price_passed.append(detail)
        else:
            context.log.info(
                "Listing %s price £%d outside [%d, %d]; excluding.",
                detail.listing_id,
                detail.price_gbp,
                config.min_budget,
                config.max_budget,
            )
    after_price = len(price_passed)

    # Filter 2: photos
    photo_passed: list[ZooplaListingDetail] = []
    for detail in price_passed:
        if config.has_images and len(detail.image_urls) <= 2:
            context.log.info(
                "Listing %s has insufficient photos (count=%d); excluding.",
                detail.listing_id,
                len(detail.image_urls),
            )
            continue
        photo_passed.append(detail)
    after_photos = len(photo_passed)

    # Filter 3: floor area — falls back to vision-extracted size when structured
    # data is absent; unknown-size listings are kept (consistent with prior behaviour).
    size_passed = _apply_size_filter(
        photo_passed,
        zoopla_extracted_floor_plans,
        config.min_square_meters,
        context.log,
    )
    after_size = len(size_passed)

    # Filter 4: isochrone
    isochrone_passed: list[ZooplaListingDetail] = []
    for detail in size_passed:
        if detail.latitude is None or detail.longitude is None:
            context.log.info(
                "Listing %s has no coordinates; skipping isochrone check.",
                detail.listing_id,
            )
            continue
        easting, northing = wgs84_to_bng(detail.longitude, detail.latitude)
        pt = Point(easting, northing)
        if isochrone_intersection and any(
            poly.contains(pt) for poly in isochrone_intersection
        ):
            isochrone_passed.append(detail)
        else:
            context.log.info(
                "Listing %s at (%.4f, %.4f) outside isochrone; skipping.",
                detail.listing_id,
                detail.latitude,
                detail.longitude,
            )
    after_isochrone = len(isochrone_passed)

    context.log.info(
        "Filters: total=%d price=%d photos=%d size=%d isochrone=%d",
        total_enriched,
        after_price,
        after_photos,
        after_size,
        after_isochrone,
    )

    if not isochrone_passed:
        context.add_output_metadata({
            "total_count": total_enriched,
            "after_price": after_price,
            "after_photos": after_photos,
            "after_size": after_size,
            "after_isochrone": after_isochrone,
            "matched_count": 0,
        })
        return []

    # Step 2: TfL commute filter
    dests = [
        CommuteDest(lon=q.lon, lat=q.lat, max_duration=q.max_duration)
        for q in queries.queries
    ]

    if not dests:
        context.log.warning(
            "No commute destinations configured; keeping all isochrone-passed listings."
        )
        return [
            _to_final_property(d, [], zoopla_extracted_floor_plans)
            for d in isochrone_passed
        ]

    flat_to_froms: list[tuple[float, float, float, float]] = [
        (detail.longitude, detail.latitude, dest.lon, dest.lat)
        for detail in isochrone_passed
        for dest in dests
        if detail.longitude is not None and detail.latitude is not None
    ]
    total = len(flat_to_froms)

    cache_path = Path(cache.data_dir) / "journey_cache.db"
    journey_cache: ModelCache[int | None] = ModelCache(
        int | None, cache_path, ttl=DEFAULT_JOURNEY_CACHE_TTL
    )

    async def _run_all() -> list[list[int | None]]:
        raw: list[int | None] = [None] * total
        received = 0
        async for idx, duration in get_properties_journey_duration_cached(
            flat_to_froms, journey_cache, tfl_resource.api_key
        ):
            raw[idx] = duration
            received += 1
            if received % 5 == 0 or received == total:
                context.log.info("Journey results: %d / %d.", received, total)
        n = len(dests)
        return [raw[i * n : (i + 1) * n] for i in range(len(isochrone_passed))]

    all_durations = asyncio.run(_run_all())

    matched: list[FinalProperty] = []
    for detail, durations in zip(isochrone_passed, all_durations, strict=False):
        if all(
            d is not None and d <= dest.max_duration
            for d, dest in zip(durations, dests, strict=False)
        ):
            matched.append(
                _to_final_property(
                    detail, list(durations), zoopla_extracted_floor_plans
                )
            )
        else:
            context.log.info(
                "Listing %s failed commute filter (durations=%s).",
                detail.listing_id,
                durations,
            )

    context.log.info(
        "%d / %d listing(s) passed commute filter.",
        len(matched),
        len(isochrone_passed),
    )
    context.add_output_metadata({
        "total_count": total_enriched,
        "after_price": after_price,
        "after_photos": after_photos,
        "after_size": after_size,
        "after_isochrone": after_isochrone,
        "matched_count": len(matched),
    })
    return matched
