"""Pure merge + size-filter asset: combines matched IDs, candidate properties,
Rightmove detail, and pre-extracted attributes into a list of FinalProperty.

All Anthropic batch work has moved to the ``extracted_attributes`` asset.
"""

import logging
from collections.abc import Iterator

import dagster as dg

import rightmove.models
from flathunt.anthropic_extraction import ExtractedAttributes
from flathunt.defs.resources import SearchCriteriaResource
from flathunt.models import FinalProperty, MatchedProperty, parse_display_size_sqm

logger = logging.getLogger(__name__)


def _to_final_property(
    prop: rightmove.models.MapProperty,
    details_result: rightmove.models.PropertyDetailsFetchResult | None,
    attrs: ExtractedAttributes,
    commute_durations: list[int | None],
) -> FinalProperty:
    """Build a FinalProperty from structured sources and pre-extracted attributes."""
    structured = details_result.details if details_result else None
    is_delisted = details_result.is_delisted if details_result else False
    lc = structured.living_costs if structured else None
    desc = attrs.description

    # Size from extracted attributes
    extracted_sqm: float | None = (
        attrs.floor_plan.total_sqm if attrs.floor_plan else None
    )
    extracted_sqm_breakdown: str | None = (
        attrs.floor_plan.breakdown_csv if attrs.floor_plan else None
    )

    # Beds/baths: prefer structured API values, fall back to LLM-extracted values
    bedrooms = (
        prop.bedrooms
        if prop.bedrooms is not None
        else (desc.bedrooms if desc else None)
    )
    bathrooms = (
        prop.bathrooms
        if prop.bathrooms is not None
        else (desc.bathrooms if desc else None)
    )

    return FinalProperty(
        id=prop.id,
        display_address=prop.display_address,
        price=prop.price,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        display_size=prop.display_size,
        extracted_sqm=extracted_sqm,
        extracted_sqm_breakdown=extracted_sqm_breakdown,
        property_url=prop.property_url,
        commute_durations=commute_durations,
        council_tax_band=lc.council_tax_band if lc else None,
        annual_ground_rent=lc.annual_ground_rent if lc else None,
        ground_rent_review_period_in_years=(
            lc.ground_rent_review_period_in_years if lc else None
        ),
        ground_rent_percentage_increase=(
            lc.ground_rent_percentage_increase if lc else None
        ),
        annual_service_charge=lc.annual_service_charge if lc else None,
        tenure_type=structured.tenure_type if structured else None,
        years_remaining_on_lease=structured.years_remaining_on_lease
        if structured
        else None,
        extracted_years_remaining_on_lease=desc.years_remaining_on_lease
        if desc
        else None,
        extracted_tenure_type=desc.tenure_type if desc else None,
        extracted_annual_service_charge=desc.annual_service_charge if desc else None,
        extracted_annual_ground_rent=desc.annual_ground_rent if desc else None,
        extracted_council_tax_band=desc.council_tax_band if desc else None,
        is_below_ground=attrs.is_below_ground(),
        is_delisted=is_delisted,
    )


@dg.asset(
    group_name="rightmove_search", io_manager_key="fs_io_manager", output_required=False
)
def matched_properties(
    context: dg.AssetExecutionContext,
    search_criteria: SearchCriteriaResource,
    matched_property_ids: list[MatchedProperty],
    candidate_properties: list[rightmove.models.MapProperty],
    rightmove_property_details: dict[int, rightmove.models.PropertyDetailsFetchResult],
    extracted_attributes: dict[str, ExtractedAttributes],
) -> Iterator[dg.Output[list[FinalProperty]] | dg.AssetObservation]:
    """Merge matched IDs with property details and extracted attributes, then filter by size.

    Consumes the output of ``extracted_attributes`` (Anthropic batch extraction) and
    combines it with structured Rightmove data to produce enriched FinalProperty objects.

    Properties where the floor area cannot be determined are kept (unknown != too small).

    Args:
        search_criteria: Contains the minimum square metres threshold.
        matched_property_ids: Properties that passed the commute filter.
        candidate_properties: Full MapProperty objects from ``candidate_properties``.
        rightmove_property_details: Detail pages keyed by property ID.
        extracted_attributes: LLM-extracted floor plan / description data keyed by
            str(property_id), from the ``extracted_attributes`` asset.

    Returns:
        FinalProperty list for properties that pass the size filter (or have unknown size).
    """
    matched_set = {m.property_id for m in matched_property_ids}
    props_by_id = {p.id: p for p in candidate_properties if p.id in matched_set}
    durations_by_id = {m.property_id: m.commute_durations for m in matched_property_ids}

    finals: list[FinalProperty] = []
    for matched in matched_property_ids:
        prop = props_by_id.get(matched.property_id)
        if prop is None:
            continue
        details_result = rightmove_property_details.get(prop.id)
        attrs = extracted_attributes.get(str(prop.id), ExtractedAttributes())
        finals.append(
            _to_final_property(
                prop, details_result, attrs, durations_by_id[matched.property_id]
            )
        )

    result = []
    below_ground_excluded = 0
    delisted_excluded = 0
    for fp in finals:
        if fp.is_delisted:
            delisted_excluded += 1
            continue
        if search_criteria.exclude_below_ground and fp.is_below_ground is True:
            below_ground_excluded += 1
            continue
        sqm = (
            parse_display_size_sqm(fp.display_size)
            if fp.display_size
            else fp.extracted_sqm
        )
        if sqm is None or sqm >= search_criteria.min_square_meters:
            result.append(fp)

    logger.info(
        "%d / %d propert(ies) remain after delisted, below-ground, and size "
        "filtering (%d excluded delisted, %d excluded below-ground).",
        len(result),
        len(finals),
        delisted_excluded,
        below_ground_excluded,
    )
    metadata = {
        "matched_count": len(matched_property_ids),
        "final_count": len(result),
    }
    if not result:
        yield dg.AssetObservation(asset_key=context.asset_key, metadata=metadata)
        return
    yield dg.Output(result, metadata=metadata)
