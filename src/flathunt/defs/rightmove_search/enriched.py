import asyncio
import logging
from pathlib import Path
from typing import Any

import dagster as dg
import httpx
import pydantic
from anthropic.types.messages.batch_create_params import Request

import rightmove.models
from flathunt.cache import ModelCache
from flathunt.defs.resources import CacheResource, SearchCriteriaResource
from flathunt.floor_plan_batch import (
    extract_json_from_response as _extract_json_from_response,
)
from flathunt.floor_plan_batch import (
    get_floor_plan_sqm as _get_floor_plan_sqm,
)
from flathunt.floor_plan_batch import (
    parse_floor_plan_result,
)
from flathunt.floor_plan_batch import (
    poll_batch_completion as _poll_batch_completion,
)
from flathunt.floor_plan_batch import (
    submit_batch as _submit_batch,
)
from flathunt.models import FinalProperty, MatchedProperty, parse_display_size_sqm
from rightmove.anthropic_config import get_client
from rightmove.description_extractor import (
    ExtractedPropertyInfo,
    PropertyDescriptionExtractor,
)
from rightmove.floor_plan import FloorPlanSizeExtractor

logger = logging.getLogger(__name__)

_FLOOR_PLAN_CACHE_TTL = 30 * 24 * 3600  # 30 days
_LEASEHOLD_CACHE_TTL = 30 * 24 * 3600  # 30 days
_LLM_CONCURRENCY = 1
_LLM_CALL_INTERVAL = 0.5  # seconds between LLM calls (Anthropic handles rate limits)


def _process_batch_results(  # type: ignore[no-untyped-def]
    batch_id: str,
    floor_plan_cache: ModelCache[tuple[float | None, str | None]],
    description_cache: ModelCache[ExtractedPropertyInfo],
    custom_id_to_meta: dict[str, dict[str, Any]],
    context: dg.AssetExecutionContext,
) -> dict[str, dict[str, list[str]]]:
    """Stream and process batch results, updating caches.

    Args:
        batch_id: The batch ID to retrieve results from
        floor_plan_cache: Cache for floor plan extraction results
        description_cache: Cache for description extraction results
        custom_id_to_meta: Map from custom_id to extraction metadata
            (type, prop_id, image_idx, etc.)
        context: Dagster execution context for logging

    Returns:
        A dict with counts of succeeded/errored/expired/canceled by type.
    """
    client = get_client()
    results_summary = {
        "floor_plan": {"succeeded": [], "errored": [], "expired": []},
        "description": {"succeeded": [], "errored": [], "expired": []},
    }

    floor_plan_updates: dict[str, tuple[float | None, str | None]] = {}
    description_updates: dict[str, ExtractedPropertyInfo] = {}

    for result in client.messages.batches.results(batch_id):
        custom_id = result.custom_id
        meta = custom_id_to_meta.get(custom_id)
        if not meta:
            logger.warning("Unknown custom_id in batch results: %s", custom_id)
            continue

        extraction_type = meta["type"]
        prop_id = str(meta["prop_id"])
        result_type = result.result.type

        if result_type == "succeeded":
            try:
                succeeded_result = result.result  # type: ignore[assignment]
                message_content = succeeded_result.message.content[0].text  # type: ignore
                json_content = _extract_json_from_response(message_content)

                if extraction_type == "floor_plan":
                    total_sqm, breakdown_csv = parse_floor_plan_result(json_content)
                    floor_plan_updates[prop_id] = (total_sqm, breakdown_csv)
                    if total_sqm is not None or breakdown_csv is not None:
                        logger.info(
                            "Floor plan %s for property %s: total=%s, breakdown=%s",
                            meta["image_idx"],
                            prop_id,
                            total_sqm,
                            breakdown_csv,
                        )
                    else:
                        logger.info(
                            "Floor plan %s for property %s returned no extraction",
                            meta["image_idx"],
                            prop_id,
                        )

                elif extraction_type == "description":
                    extraction = pydantic.TypeAdapter(
                        ExtractedPropertyInfo
                    ).validate_json(json_content)
                    description_updates[prop_id] = extraction
                    logger.info(
                        "Description for property %s: %s",
                        prop_id,
                        extraction.model_dump(exclude_none=True),
                    )

                results_summary[extraction_type]["succeeded"].append(custom_id)

            except (ValueError, pydantic.ValidationError) as e:
                logger.exception(
                    "Failed to parse %s extraction for %s: %s",
                    extraction_type,
                    custom_id,
                    e,
                )
                results_summary[extraction_type]["errored"].append(custom_id)

        elif result_type == "errored":
            errored_result = result.result  # type: ignore[assignment]
            logger.error(
                "Batch request %s errored: %s",
                custom_id,
                errored_result.error.error.type,  # type: ignore
            )
            results_summary[extraction_type]["errored"].append(custom_id)

        elif result_type == "expired":
            logger.error("Batch request %s expired after 24 hours", custom_id)
            results_summary[extraction_type]["expired"].append(custom_id)

    # Update caches with successful extractions
    if floor_plan_updates:
        floor_plan_cache.update(list(floor_plan_updates.items()))
        context.log.info(
            "Updated floor plan cache with %d entries", len(floor_plan_updates)
        )

    if description_updates:
        description_cache.update(list(description_updates.items()))
        context.log.info(
            "Updated description cache with %d entries", len(description_updates)
        )

    return results_summary


def _parse_display_size(display_size: str | None) -> float | None:
    """Return the floor area in square metres, or None if not present or not parseable."""
    if not display_size:
        return None
    if display_size.endswith(" sq. ft."):
        sq_ft = int(display_size.removesuffix(" sq. ft.").replace(",", ""))
        return sq_ft * 0.092903
    if display_size.endswith(" sq. m."):
        return float(display_size.removesuffix(" sq. m.").replace(",", ""))
    if display_size.endswith(" sqm"):
        return float(display_size.removesuffix(" sqm").replace(",", ""))
    return None


async def _get_description_info(
    prop_id: int,
    details: rightmove.models.PropertyDetails | None,
    cache: ModelCache[ExtractedPropertyInfo],
    extractor: PropertyDescriptionExtractor,
    llm_semaphore: asyncio.Semaphore,
) -> ExtractedPropertyInfo:
    """Return extracted property info, using cache or LLM extraction.

    Only writes to the cache on a successful extraction attempt so that
    transient failures (network errors, rate limits) are retried on the
    next run rather than being permanently recorded as missing.
    """
    cache_key = str(prop_id)
    try:
        return cache.get(cache_key)
    except KeyError:
        pass

    info = ExtractedPropertyInfo()
    try:
        description = details.description if details else None
        if not description:
            logger.warning(
                "Property %d has no description for info extraction.", prop_id
            )
        else:
            async with llm_semaphore:
                info = await extractor.extract(description)
                await asyncio.sleep(_LLM_CALL_INTERVAL)

            logger.info(
                "Extracted description info for property %d: %s",
                prop_id,
                info.model_dump(exclude_none=True),
            )
        cache.update([(cache_key, info)])
    except Exception:
        logger.exception(
            "Failed to extract description info for property %d — keeping property.",
            prop_id,
        )

    return info


async def _process_property(
    prop: rightmove.models.MapProperty,
    matched: MatchedProperty,
    needs_extraction: bool,
    floor_plan_cache: ModelCache[tuple[float | None, str | None]],
    description_info_cache: ModelCache[ExtractedPropertyInfo],
    details: rightmove.models.PropertyDetails | None,
    extractor: FloorPlanSizeExtractor,
    description_extractor: PropertyDescriptionExtractor,
    llm_semaphore: asyncio.Semaphore,
) -> FinalProperty:
    """Optionally extract floor plan size from details, then build a FinalProperty."""
    extracted_sqm: float | None = None
    extracted_sqm_breakdown: str | None = None
    if needs_extraction:
        extracted_sqm, extracted_sqm_breakdown = await _get_floor_plan_sqm(
            prop.id,
            details,
            floor_plan_cache,
            extractor,
            llm_semaphore,
        )
        await asyncio.sleep(_LLM_CALL_INTERVAL)

    api_years = details.years_remaining_on_lease if details else None
    desc_info = await _get_description_info(
        prop.id,
        details,
        description_info_cache,
        description_extractor,
        llm_semaphore,
    )

    lc = details.living_costs if details else None
    return FinalProperty(
        id=prop.id,
        display_address=prop.display_address,
        price=prop.price,
        bedrooms=prop.bedrooms,
        bathrooms=prop.bathrooms,
        display_size=prop.display_size,
        extracted_sqm=extracted_sqm,
        extracted_sqm_breakdown=extracted_sqm_breakdown,
        property_url=prop.property_url,
        commute_durations=matched.commute_durations,
        council_tax_band=lc.council_tax_band if lc else None,
        annual_ground_rent=lc.annual_ground_rent if lc else None,
        ground_rent_review_period_in_years=(
            lc.ground_rent_review_period_in_years if lc else None
        ),
        ground_rent_percentage_increase=(
            lc.ground_rent_percentage_increase if lc else None
        ),
        annual_service_charge=lc.annual_service_charge if lc else None,
        tenure_type=details.tenure_type if details else None,
        years_remaining_on_lease=api_years,
        extracted_years_remaining_on_lease=desc_info.years_remaining_on_lease,
        extracted_tenure_type=desc_info.tenure_type,
        extracted_annual_service_charge=desc_info.annual_service_charge,
        extracted_annual_ground_rent=desc_info.annual_ground_rent,
        extracted_council_tax_band=desc_info.council_tax_band,
    )


@dg.asset(group_name="rightmove_search", io_manager_key="fs_io_manager")
def enriched_properties(
    context: dg.AssetExecutionContext,
    search_criteria: SearchCriteriaResource,
    cache: CacheResource,
    matched_property_ids: list[MatchedProperty],
    candidate_properties: list[rightmove.models.MapProperty],
    rightmove_property_details: dict[int, rightmove.models.PropertyDetails | None],
) -> list[FinalProperty]:
    """Enrich matched properties with living costs and filter by floor area.

    Fetches the Rightmove property details page for every matched property to
    obtain living costs (council tax band, ground rent, service charge, tenure).
    For properties whose ``display_size`` is absent and have floor plan images,
    each floor plan is passed to :class:`FloorPlanSizeExtractor` to read the
    size annotation. The extractor intelligently handles multiple floor plans:
    - Prefers total size if clearly labeled
    - Falls back to per-floor breakdown if only individual sizes available
    - Returns nothing if ambiguous. LLM calls are serialised (one at a time) with
    a 5-second gap between them.

    Properties where the floor area cannot be determined are kept.

    Args:
        config: Size threshold for filtering properties.
        cache: CacheResource providing cache directory.
        matched_property_ids: Properties that passed the commute filter, with
            per-destination durations, as produced by ``matched_property_ids``.
        candidate_properties: Full property objects from ``candidate_properties``.

    Returns:
        A list of :class:`FinalProperty` values containing all enriched data for
        properties whose floor area meets ``min_square_meters``.
    """
    if not matched_property_ids:
        return []

    matched_set = {m.property_id for m in matched_property_ids}
    props_by_id = {p.id: p for p in candidate_properties if p.id in matched_set}

    floor_plan_cache_path = Path(cache.data_dir) / "floor_plan_size_cache.db"
    floor_plan_cache: ModelCache[tuple[float | None, str | None]] = ModelCache(
        tuple[float | None, str | None],
        floor_plan_cache_path,
        ttl=_FLOOR_PLAN_CACHE_TTL,
    )

    description_info_cache_path = Path(cache.data_dir) / "description_info_cache.db"
    description_info_cache: ModelCache[ExtractedPropertyInfo] = ModelCache(
        ExtractedPropertyInfo,
        description_info_cache_path,
        ttl=_LEASEHOLD_CACHE_TTL,
    )

    extractor = FloorPlanSizeExtractor()
    description_extractor = PropertyDescriptionExtractor()

    async def _run_all() -> tuple[list[FinalProperty], int]:
        llm_semaphore = asyncio.Semaphore(_LLM_CONCURRENCY)

        # PHASE 1: Collect all batch requests for floor plans and descriptions
        context.log.info("Phase 1: Collecting batch requests...")
        batch_requests: list[Request] = []
        custom_id_to_meta: dict[str, dict] = {}

        for matched in matched_property_ids:
            prop = props_by_id.get(matched.property_id)
            if prop is None:
                continue

            details = rightmove_property_details.get(prop.id)
            cache_key = str(prop.id)

            # Collect floor plan batch requests (skip if cached)
            metadata_sqm = _parse_display_size(prop.display_size)
            floor_plan_cached = False
            if metadata_sqm is None:
                try:
                    floor_plan_cache.peek(cache_key)
                    floor_plan_cached = True
                    logger.debug("Floor plan cache hit for property %d.", prop.id)
                except KeyError:
                    pass

            if (
                metadata_sqm is None
                and not floor_plan_cached
                and details
                and details.floorplans
            ):
                for image_idx, floor_plan in enumerate(details.floorplans):
                    try:
                        async with httpx.AsyncClient() as http_client:
                            response = await http_client.get(
                                floor_plan.url, timeout=30.0
                            )
                            response.raise_for_status()

                        custom_id = f"fp_{prop.id}_{image_idx}"
                        request = extractor.build_batch_request(
                            custom_id, response.content
                        )
                        batch_requests.append(request)
                        custom_id_to_meta[custom_id] = {
                            "type": "floor_plan",
                            "prop_id": prop.id,
                            "image_idx": image_idx,
                        }
                    except Exception:
                        logger.exception(
                            "Failed to download floor plan %d for property %d",
                            image_idx,
                            prop.id,
                        )

            # Collect description batch requests (skip if cached)
            description_cached = False
            try:
                description_info_cache.peek(cache_key)
                description_cached = True
                logger.debug("Description cache hit for property %d.", prop.id)
            except KeyError:
                pass

            if not description_cached and details and details.description:
                custom_id = f"desc_{prop.id}"
                request = description_extractor.build_batch_request(
                    custom_id, details.description
                )
                batch_requests.append(request)
                custom_id_to_meta[custom_id] = {
                    "type": "description",
                    "prop_id": prop.id,
                }

        context.log.info("Collected %d extraction requests", len(batch_requests))
        batch_request_count = len(batch_requests)

        # PHASE 2: Submit batch and poll for completion
        if batch_requests:
            context.log.info("Phase 2: Submitting batch...")
            batch_id = _submit_batch(batch_requests, context)
            await _poll_batch_completion(batch_id, context)
            context.log.info("Phase 2: Processing batch results...")
            _process_batch_results(
                batch_id,
                floor_plan_cache,
                description_info_cache,
                custom_id_to_meta,
                context,
            )
        else:
            context.log.info("No extraction requests collected, skipping batch phase")

        # PHASE 3: Process properties using cached results
        context.log.info("Phase 3: Building final properties...")
        tasks = []
        for matched in matched_property_ids:
            prop = props_by_id.get(matched.property_id)
            if prop is None:
                continue
            tasks.append(
                _process_property(
                    prop,
                    matched,
                    True,  # always attempt extraction; _get_floor_plan_sqm checks cache first
                    floor_plan_cache,
                    description_info_cache,
                    rightmove_property_details.get(prop.id),
                    extractor,
                    description_extractor,
                    llm_semaphore,
                )
            )

        total = len(tasks)
        results = []
        for i, coro in enumerate(asyncio.as_completed(tasks), start=1):
            results.append(await coro)
            context.log.info("Enriched property %d / %d.", i, total)
        return results, batch_request_count

    final_properties, batch_request_count = asyncio.run(_run_all())

    result = []
    for fp in final_properties:
        sqm = (
            parse_display_size_sqm(fp.display_size)
            if fp.display_size
            else fp.extracted_sqm
        )
        if sqm is None or sqm >= search_criteria.min_square_meters:
            result.append(fp)

    logger.info(
        "%d / %d propert(ies) remain after floor plan size filtering.",
        len(result),
        len(final_properties),
    )
    context.add_output_metadata({
        "matched_count": len(matched_property_ids),
        "batch_request_count": batch_request_count,
        "final_count": len(result),
    })
    return result
