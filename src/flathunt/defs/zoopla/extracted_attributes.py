"""Zoopla attribute extraction via the shared Anthropic batch layer."""

import logging
from pathlib import Path

import dagster as dg

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
from flathunt.models import MatchedProperty
from zoopla.models import ZooplaListingDetail

logger = logging.getLogger(__name__)

__all__ = ["zoopla_extracted_attributes"]


@dg.asset(group_name="zoopla", io_manager_key="fs_io_manager")
async def zoopla_extracted_attributes(
    context: dg.AssetExecutionContext,
    cache: CacheResource,
    zoopla_matched_ids: list[MatchedProperty],
    zoopla_candidate_properties: list[ZooplaListingDetail],
) -> dict[str, ExtractedAttributes]:
    detail_by_id = {d.listing_id: d for d in zoopla_candidate_properties}
    fp_cache: ModelCache[FloorPlanResult] = ModelCache(
        FloorPlanResult,
        Path(cache.data_dir) / "zoopla_floor_plan_cache.db",
        ttl=FLOOR_PLAN_CACHE_TTL,
    )
    desc_cache: ModelCache[ExtractedPropertyInfo] = ModelCache(
        ExtractedPropertyInfo,
        Path(cache.data_dir) / "zoopla_description_cache.db",
        ttl=DESCRIPTION_CACHE_TTL,
    )

    inputs: list[ListingExtractionInput] = []
    for matched in zoopla_matched_ids:
        detail = detail_by_id.get(str(matched.property_id))
        if detail is None:
            continue
        inputs.append(
            ListingExtractionInput(
                listing_id=detail.listing_id,
                description=detail.description,
                floor_plan_image_urls=detail.floorplan_urls,
                needs_floor_plan=detail.floor_area_sqft is None
                and bool(detail.floorplan_urls),
                # Zoopla has no structured lease-years field, so any listing with a
                # description is eligible — lease-years alone forces the description call.
                needs_description=detail.description is not None,
            )
        )

    result = await extract_attributes(inputs, fp_cache, desc_cache, context)
    context.add_output_metadata({
        "matched_count": len(zoopla_matched_ids),
        "extracted_count": len(result),
    })
    return result
