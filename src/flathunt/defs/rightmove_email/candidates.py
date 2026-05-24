import dagster as dg
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon

from flathunt.defs.resources import SearchCriteriaResource
from flathunt.geometry import wgs84_to_bng
from flathunt.models import FinalProperty
from rightmove.email_models import RightmoveProperty, RightmovePropertyAlert

__all__ = ["rightmove_email_candidate_properties"]


@dg.asset(group_name="rightmove_email")
def rightmove_email_candidate_properties(
    context: dg.AssetExecutionContext,
    search_criteria: SearchCriteriaResource,
    rightmove_property_alerts: list[RightmovePropertyAlert],
    rightmove_enriched_properties: list[FinalProperty],
    isochrone_intersection: list[Polygon],
) -> list[FinalProperty]:
    """Filter enriched Rightmove email properties by cheap criteria.

    Applies price, floorplan count, photo count, and isochrone filters so that
    only viable candidates reach the commute stage.  All filters are NULL-SAFE:
    a property is rejected ONLY when the relevant value is present AND fails the
    test.  Unknown values always pass.

    Args:
        context: Dagster execution context.
        search_criteria: Budget, image, and floorplan thresholds.
        rightmove_property_alerts: Raw email alert objects keyed by listing_id.
        rightmove_enriched_properties: Enriched FinalProperty objects from the
            email pipeline.
        isochrone_intersection: BNG polygons defining the reachable area.

    Returns:
        Properties that pass all cheap filters.
    """
    # Build lookup: listing_id → RightmoveProperty (first occurrence wins).
    email_by_id: dict[str, RightmoveProperty] = {}
    for alert in rightmove_property_alerts:
        for prop in alert.properties:
            email_by_id.setdefault(prop.listing_id, prop)

    total = len(rightmove_enriched_properties)

    # Filter 1: price — null-safe: unknown price passes (cannot rule out in-budget).
    price_passed: list[FinalProperty] = []
    for prop in rightmove_enriched_properties:
        amount = prop.price.amount if prop.price else None
        if amount is None:
            context.log.info(
                "Property %s has no price; keeping as price-unknown.", prop.id
            )
            price_passed.append(prop)
        elif search_criteria.min_budget <= amount <= search_criteria.max_budget:
            price_passed.append(prop)
        else:
            context.log.info(
                "Property %s price £%d outside [%d, %d]; excluding.",
                prop.id,
                amount,
                search_criteria.min_budget,
                search_criteria.max_budget,
            )
    after_price = len(price_passed)

    # Filter 2: floorplans — null-safe: unknown count passes (cannot confirm absence).
    floorplan_passed: list[FinalProperty] = []
    for prop in price_passed:
        if search_criteria.has_floorplans:
            ep = email_by_id.get(str(prop.id))
            count = ep.floorplan_count if ep is not None else None
            if count is None:
                context.log.info(
                    "Property %s has unknown floorplan count; keeping as floorplan-unknown.",
                    prop.id,
                )
            elif count == 0:
                context.log.info(
                    "Property %s has no floorplans (count=0); excluding.", prop.id
                )
                continue
        floorplan_passed.append(prop)
    after_floorplans = len(floorplan_passed)

    # Filter 3: photos — null-safe: unknown count passes (cannot confirm insufficient).
    photo_passed: list[FinalProperty] = []
    for prop in floorplan_passed:
        if search_criteria.has_images:
            ep = email_by_id.get(str(prop.id))
            count = ep.photo_count if ep is not None else None
            if count is None:
                context.log.info(
                    "Property %s has unknown photo count; keeping as photo-unknown.",
                    prop.id,
                )
            elif count <= 2:
                context.log.info(
                    "Property %s has insufficient photos (count=%d); excluding.",
                    prop.id,
                    count,
                )
                continue
        photo_passed.append(prop)
    after_photos = len(photo_passed)

    # Filter 4: isochrone — null-safe: unknown coordinates pass (commute-unknown path).
    isochrone_passed: list[FinalProperty] = []
    for prop in photo_passed:
        if prop.latitude is None or prop.longitude is None:
            context.log.info(
                "Property %s has no coordinates; keeping as commute-unknown.", prop.id
            )
            isochrone_passed.append(prop)
            continue
        easting, northing = wgs84_to_bng(prop.longitude, prop.latitude)
        pt = Point(easting, northing)
        if isochrone_intersection and any(
            poly.contains(pt) for poly in isochrone_intersection
        ):
            isochrone_passed.append(prop)
        else:
            context.log.info(
                "Property %s at (%.4f, %.4f) outside isochrone; excluding.",
                prop.id,
                prop.latitude,
                prop.longitude,
            )
    after_isochrone = len(isochrone_passed)

    context.log.info(
        "Candidate filters: total=%d price=%d floorplans=%d photos=%d isochrone=%d",
        total,
        after_price,
        after_floorplans,
        after_photos,
        after_isochrone,
    )
    context.add_output_metadata({
        "total_count": total,
        "after_price": after_price,
        "after_floorplans": after_floorplans,
        "after_photos": after_photos,
        "after_isochrone": after_isochrone,
        "candidate_count": after_isochrone,
    })
    return isochrone_passed
