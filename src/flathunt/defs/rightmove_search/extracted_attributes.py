"""Rightmove-search attribute extraction via the shared Anthropic batch layer."""

import logging
from pathlib import Path

import dagster as dg

import rightmove.models
from flathunt.anthropic_extraction import (
    DESCRIPTION_CACHE_TTL,
    FLOOR_PLAN_CACHE_TTL,
    ExtractedAttributes,
    ExtractedPropertyInfo,
    FloorPlanResult,
    ListingExtractionInput,
    extract_attributes,
)
from flathunt.cache import ModelCache
from flathunt.defs.resources import CacheResource
from flathunt.models import MatchedProperty, parse_display_size_sqm

logger = logging.getLogger(__name__)

__all__ = ["extracted_attributes"]


def _rightmove_needs_description(
    details: rightmove.models.PropertyDetails | None,
) -> bool:
    if details is None:
        return False
    lc = details.living_costs
    return any(
        v is None
        for v in (
            details.tenure_type,
            details.years_remaining_on_lease,
            lc.annual_service_charge,
            lc.annual_ground_rent,
            lc.council_tax_band,
            details.bedrooms,
            details.bathrooms,
        )
    )


@dg.asset(group_name="rightmove_search", io_manager_key="fs_io_manager")
async def extracted_attributes(
    context: dg.AssetExecutionContext,
    cache: CacheResource,
    matched_property_ids: list[MatchedProperty],
    candidate_properties: list[rightmove.models.MapProperty],
    rightmove_property_details: dict[int, rightmove.models.PropertyDetails | None],
) -> dict[str, ExtractedAttributes]:
    matched_set = {m.property_id for m in matched_property_ids}
    props_by_id = {p.id: p for p in candidate_properties if p.id in matched_set}

    fp_cache: ModelCache[FloorPlanResult] = ModelCache(
        FloorPlanResult,
        Path(cache.data_dir) / "floor_plan_cache.db",
        ttl=FLOOR_PLAN_CACHE_TTL,
    )
    desc_cache: ModelCache[ExtractedPropertyInfo] = ModelCache(
        ExtractedPropertyInfo,
        Path(cache.data_dir) / "description_cache.db",
        ttl=DESCRIPTION_CACHE_TTL,
    )

    inputs: list[ListingExtractionInput] = []
    for matched in matched_property_ids:
        prop = props_by_id.get(matched.property_id)
        if prop is None:
            continue
        details = rightmove_property_details.get(prop.id)
        size_known = parse_display_size_sqm(prop.display_size) is not None or (
            details is not None and details.size_sqm is not None
        )
        urls = (
            [fp.url for fp in details.floorplans]
            if details and details.floorplans
            else []
        )
        inputs.append(
            ListingExtractionInput(
                listing_id=str(prop.id),
                description=details.description if details else None,
                floor_plan_image_urls=urls,
                needs_floor_plan=(not size_known) and bool(urls),
                needs_description=_rightmove_needs_description(details)
                and bool(details and details.description),
            )
        )

    result = await extract_attributes(inputs, fp_cache, desc_cache, context)
    context.add_output_metadata({
        "matched_count": len(matched_property_ids),
        "extracted_count": len(result),
    })
    return result
