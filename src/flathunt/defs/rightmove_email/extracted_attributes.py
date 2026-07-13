"""Rightmove-email attribute extraction via the shared Anthropic batch layer."""

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
from flathunt.defs.rightmove_search.extracted_attributes import (
    rightmove_needs_description,
)
from flathunt.models import MatchedProperty

logger = logging.getLogger(__name__)

__all__ = ["rightmove_email_extracted_attributes"]


@dg.asset(group_name="rightmove_email", io_manager_key="fs_io_manager")
async def rightmove_email_extracted_attributes(
    context: dg.AssetExecutionContext,
    cache: CacheResource,
    rightmove_email_matched_ids: list[MatchedProperty],
    rightmove_email_property_details: dict[
        str, rightmove.models.PropertyDetailsFetchResult
    ],
) -> dict[str, ExtractedAttributes]:
    fp_cache: ModelCache[FloorPlanResult] = ModelCache(
        FloorPlanResult,
        Path(cache.data_dir) / "rightmove_email_floor_plan_cache.db",
        ttl=FLOOR_PLAN_CACHE_TTL,
    )
    desc_cache: ModelCache[ExtractedPropertyInfo] = ModelCache(
        ExtractedPropertyInfo,
        Path(cache.data_dir) / "rightmove_email_description_cache.db",
        ttl=DESCRIPTION_CACHE_TTL,
    )

    inputs: list[ListingExtractionInput] = []
    for matched in rightmove_email_matched_ids:
        listing_id = str(matched.property_id)
        details_result = rightmove_email_property_details.get(listing_id)
        details = details_result.details if details_result else None
        urls = (
            [fp.url for fp in details.floorplans]
            if details and details.floorplans
            else []
        )
        inputs.append(
            ListingExtractionInput(
                listing_id=listing_id,
                description=details.description if details else None,
                floor_plan_image_urls=urls,
                needs_floor_plan=(details is not None and details.size_sqm is None)
                and bool(urls),
                needs_description=rightmove_needs_description(details)
                and bool(details and details.description),
            )
        )

    result = await extract_attributes(inputs, fp_cache, desc_cache, context)
    context.add_output_metadata({
        "matched_count": len(rightmove_email_matched_ids),
        "extracted_count": len(result),
    })
    return result
