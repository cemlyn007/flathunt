import logging

import dagster as dg

from flathunt.models import FinalProperty, MatchedProperty
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
    min_square_meters: float


@dg.asset(group_name="zoopla")
def zoopla_matched_properties(
    context: dg.AssetExecutionContext,
    config: Config,
    zoopla_matched_ids: list[MatchedProperty],
    zoopla_candidate_properties: list[ZooplaListingDetail],
    zoopla_extracted_floor_plans: dict[str, tuple[float | None, str | None]],
) -> list[FinalProperty]:
    """Assemble final Zoopla properties after applying the size filter.

    All cheap filters (price, photos, isochrone) and the commute filter have
    already been applied upstream.  This asset applies a final size check that
    can fall back to vision-extracted floor areas, then builds the
    :class:`FinalProperty` output list.  Mirrors the final filtering step in
    Rightmove's ``enriched_properties`` asset.

    Args:
        context: Dagster execution context.
        config: Minimum floor area threshold.
        zoopla_matched_ids: Listings that passed all upstream filters.
        zoopla_candidate_properties: Full detail objects for candidate listings.
        zoopla_extracted_floor_plans: Vision-extracted sizes keyed by listing_id.

    Returns:
        Final properties ready for notification.
    """
    if not zoopla_matched_ids:
        context.log.info("No matched Zoopla listings; returning empty list.")
        context.add_output_metadata({"total_count": 0, "matched_count": 0})
        return []

    detail_by_id = {d.listing_id: d for d in zoopla_candidate_properties}
    durations_by_id = {
        str(m.property_id): m.commute_durations for m in zoopla_matched_ids
    }

    matched_details = [
        detail_by_id[str(m.property_id)]
        for m in zoopla_matched_ids
        if str(m.property_id) in detail_by_id
    ]
    total = len(matched_details)

    size_passed = _apply_size_filter(
        matched_details,
        zoopla_extracted_floor_plans,
        config.min_square_meters,
        context.log,
    )

    context.log.info(
        "Size filter: total=%d passed=%d",
        total,
        len(size_passed),
    )

    result = [
        _to_final_property(
            detail,
            durations_by_id.get(detail.listing_id, []),
            zoopla_extracted_floor_plans,
        )
        for detail in size_passed
    ]

    context.add_output_metadata({
        "total_count": total,
        "matched_count": len(result),
    })
    return result
