import logging

import dagster as dg
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon

from flathunt.defs.resources import SearchCriteriaResource
from flathunt.geometry import wgs84_to_bng
from rightmove.floor_plan import _SQFT_TO_SQM
from zoopla.models import ZooplaListingDetail

logger = logging.getLogger(__name__)


@dg.asset(group_name="zoopla")
def zoopla_candidate_properties(
    context: dg.AssetExecutionContext,
    search_criteria: SearchCriteriaResource,
    zoopla_enriched_properties: list[ZooplaListingDetail],
    isochrone_intersection: list[Polygon],
) -> list[ZooplaListingDetail]:
    """Filter enriched Zoopla listings by cheap criteria before AI extraction.

    Applies price, photo count, isochrone, and structured-size filters so that
    only viable candidates reach the Anthropic floor-plan batch.  Mirrors
    ``candidate_properties`` in the Rightmove pipeline.

    Args:
        context: Dagster execution context.
        config: Budget, image, and size thresholds.
        zoopla_enriched_properties: All enriched Zoopla listings.
        isochrone_intersection: BNG polygons defining the reachable area.

    Returns:
        Listings that pass all cheap filters.
    """
    total = len(zoopla_enriched_properties)

    # Filter 1: price — null-safe: unknown price passes (cannot rule out in-budget).
    price_passed: list[ZooplaListingDetail] = []
    for detail in zoopla_enriched_properties:
        if detail.price_gbp is None:
            context.log.info(
                "Listing %s has no price; keeping as price-unknown.", detail.listing_id
            )
            price_passed.append(detail)
        elif (
            search_criteria.min_budget <= detail.price_gbp <= search_criteria.max_budget
        ):
            price_passed.append(detail)
        else:
            context.log.info(
                "Listing %s price £%d outside [%d, %d]; excluding.",
                detail.listing_id,
                detail.price_gbp,
                search_criteria.min_budget,
                search_criteria.max_budget,
            )
    after_price = len(price_passed)

    # Filter 2: photos
    photo_passed: list[ZooplaListingDetail] = []
    for detail in price_passed:
        if search_criteria.has_images and len(detail.image_urls) <= 2:
            context.log.info(
                "Listing %s has insufficient photos (count=%d); excluding.",
                detail.listing_id,
                len(detail.image_urls),
            )
            continue
        photo_passed.append(detail)
    after_photos = len(photo_passed)

    # Filter 3: isochrone — null-safe: unknown coordinates pass (commute-unknown path).
    isochrone_passed: list[ZooplaListingDetail] = []
    for detail in photo_passed:
        if detail.latitude is None or detail.longitude is None:
            context.log.info(
                "Listing %s has no coordinates; keeping as commute-unknown.",
                detail.listing_id,
            )
            isochrone_passed.append(detail)
            continue
        easting, northing = wgs84_to_bng(detail.longitude, detail.latitude)
        pt = Point(easting, northing)
        if isochrone_intersection and any(
            poly.contains(pt) for poly in isochrone_intersection
        ):
            isochrone_passed.append(detail)
        else:
            context.log.info(
                "Listing %s at (%.4f, %.4f) outside isochrone; excluding.",
                detail.listing_id,
                detail.latitude,
                detail.longitude,
            )
    after_isochrone = len(isochrone_passed)

    # Filter 4: cheap size — only structured floor_area_sqft; unknown size passes.
    size_passed: list[ZooplaListingDetail] = []
    for detail in isochrone_passed:
        if detail.floor_area_sqft is not None:
            sqm = detail.floor_area_sqft * _SQFT_TO_SQM
            if sqm < search_criteria.min_square_meters:
                context.log.info(
                    "Listing %s structured size %.1f sqm below minimum %.1f; excluding.",
                    detail.listing_id,
                    sqm,
                    search_criteria.min_square_meters,
                )
                continue
        size_passed.append(detail)
    after_size = len(size_passed)

    context.log.info(
        "Candidate filters: total=%d price=%d photos=%d isochrone=%d size=%d",
        total,
        after_price,
        after_photos,
        after_isochrone,
        after_size,
    )
    context.add_output_metadata({
        "total_count": total,
        "after_price": after_price,
        "after_photos": after_photos,
        "after_isochrone": after_isochrone,
        "after_size": after_size,
        "candidate_count": after_size,
    })
    return size_passed
