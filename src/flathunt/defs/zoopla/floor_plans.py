"""Zoopla floor plan extraction asset.

Extracts floor plan sizes from Zoopla listings using :class:`FloorPlanSizeExtractor`
and an Anthropic message batch.  Sits between ``zoopla_matched_ids`` and
``zoopla_matched_properties`` in the pipeline, processing only listings that have
already passed all cheap filters and the TfL commute check.

Three-phase flow:
  1. Collect batch requests — skip cached; skip listings with structured size data or
     no URLs; download each floor plan image and build a batch request per image.
  2. Submit batch + poll for completion.
  3. Stream results, aggregate per-listing, update cache, build output dict.
"""

import asyncio
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import dagster as dg
import httpx
import pydantic
from anthropic.types.messages.batch_create_params import Request

from flathunt.anthropic_extraction import (
    extract_json_from_response,
    poll_batch_completion,
    submit_batch,
)
from flathunt.cache import ModelCache
from flathunt.defs.resources import CacheResource
from flathunt.models import MatchedProperty
from rightmove.anthropic_config import get_client
from rightmove.floor_plan import FloorPlanExtraction, FloorPlanSizeExtractor
from zoopla.models import ZooplaListingDetail

logger = logging.getLogger(__name__)

_FLOOR_PLAN_CACHE_TTL = 30 * 24 * 3600  # 30 days


def _stream_batch_results(batch_id: str) -> Iterable[Any]:
    """Return an iterable of batch results for *batch_id*.

    Factored out as a named function so tests can patch it with a plain list,
    avoiding the need to mock the full Anthropic client chain.
    """
    client = get_client()
    return client.messages.batches.results(batch_id)


def _aggregate_floor_plan_extractions(
    extractions: list[FloorPlanExtraction | None],
) -> tuple[float | None, str | None]:
    """Aggregate multiple per-image floor plan extractions for a single listing.

    Strategy (mirrors ``_extract_all_floor_plans`` in the Rightmove module):
    - Prefer the first extraction with an explicit ``total`` field set.
    - Otherwise use the first extraction that has a ``breakdown``.
    - Otherwise ``(None, None)``.

    Using the raw ``FloorPlanExtraction.total`` field (not the derived
    ``get_total_sqm()``) ensures a breakdown-only image does not "win" over a
    later image that has an explicit total.
    """
    non_none = [e for e in extractions if e is not None]

    for extraction in non_none:
        if extraction.total is not None:
            return extraction.get_total_sqm(), extraction.get_breakdown_csv()

    for extraction in non_none:
        if extraction.breakdown:
            return extraction.get_total_sqm(), extraction.get_breakdown_csv()

    return (None, None)


@dg.asset(group_name="zoopla", io_manager_key="fs_io_manager")
def zoopla_extracted_floor_plans(
    context: dg.AssetExecutionContext,
    cache: CacheResource,
    zoopla_matched_ids: list[MatchedProperty],
    zoopla_candidate_properties: list[ZooplaListingDetail],
) -> dict[str, tuple[float | None, str | None]]:
    """Extract floor plan sizes from matched Zoopla listings via Anthropic batch API.

    Only processes listings that appear in ``zoopla_matched_ids`` (i.e. those
    that have already passed all cheap filters and the TfL commute check).
    Mirrors the scoping applied in the Rightmove ``enriched_properties`` asset.

    For each qualifying listing where ``floor_area_sqft`` is absent and
    ``floorplan_urls`` is non-empty, downloads every floor plan image and submits
    it to an Anthropic message batch for vision extraction.  Results are cached
    in a 30-day SQLite cache keyed by ``listing_id``.

    Args:
        context: Dagster execution context.
        cache: Cache resource providing the data directory.
        zoopla_matched_ids: Listings that passed all cheap filters and commute check.
        zoopla_candidate_properties: Full detail objects for candidate listings.

    Returns:
        A dict mapping ``listing_id`` → ``(total_sqm, breakdown_csv)`` for
        every listing where extraction was attempted (even if it returned
        ``(None, None)``).
    """
    floor_plan_cache: ModelCache[tuple[float | None, str | None]] = ModelCache(
        tuple[float | None, str | None],
        Path(cache.data_dir) / "zoopla_floor_plan_size_cache.db",
        ttl=_FLOOR_PLAN_CACHE_TTL,
    )

    extractor = FloorPlanSizeExtractor()

    async def _run_all() -> dict[str, tuple[float | None, str | None]]:
        # PHASE 1: Collect batch requests
        context.log.info("Phase 1: Collecting batch requests...")
        batch_requests: list[Request] = []
        # custom_id → {listing_id, image_idx}
        custom_id_to_meta: dict[str, dict[str, Any]] = {}
        # Listings whose cached value we already have
        cached_results: dict[str, tuple[float | None, str | None]] = {}
        # Listings for which we submitted at least one batch request
        submitted_listing_ids: set[str] = set()

        detail_by_id = {d.listing_id: d for d in zoopla_candidate_properties}

        for matched in zoopla_matched_ids:
            listing_id = str(matched.property_id)
            detail = detail_by_id.get(listing_id)
            if detail is None:
                logger.warning(
                    "Matched listing %s not found in candidate properties; skipping.",
                    listing_id,
                )
                continue

            # Structured size already available — skip silently.
            if detail.floor_area_sqft is not None:
                continue

            # No floor plan images to extract from — log and skip.
            if not detail.floorplan_urls:
                logger.info(
                    "Listing %s: no floor plan URLs to extract from — skipping.",
                    listing_id,
                )
                continue

            # Check cache — if hit, stash for output and move on.
            cache_key = listing_id
            try:
                cached_value, _ = floor_plan_cache.peek(cache_key)
                logger.debug("Floor plan cache hit for listing %s.", listing_id)
                cached_results[listing_id] = cached_value
                continue
            except KeyError:
                pass

            # Download and build a batch request for each floor plan image.
            for image_idx, url in enumerate(detail.floorplan_urls):
                try:
                    async with httpx.AsyncClient() as http_client:
                        response = await http_client.get(url, timeout=30.0)
                        response.raise_for_status()

                    custom_id = f"fp_{listing_id}_{image_idx}"
                    request = extractor.build_batch_request(custom_id, response.content)
                    batch_requests.append(request)
                    custom_id_to_meta[custom_id] = {
                        "listing_id": listing_id,
                        "image_idx": image_idx,
                    }
                    submitted_listing_ids.add(listing_id)
                except Exception:
                    logger.exception(
                        "Failed to download floor plan %d for listing %s — skipping image.",
                        image_idx,
                        listing_id,
                    )

        context.log.info(
            "Collected %d floor plan batch request(s).", len(batch_requests)
        )

        # PHASE 2: Submit batch and poll for completion.
        # Maps listing_id → per-image FloorPlanExtraction (or None on failure).
        per_image_extractions: dict[str, list[FloorPlanExtraction | None]] = {}

        if batch_requests:
            context.log.info("Phase 2: Submitting batch...")
            batch_id = submit_batch(batch_requests, context)
            await poll_batch_completion(batch_id, context)

            context.log.info("Phase 2: Processing batch results...")
            loop = asyncio.get_running_loop()
            batch_results = await loop.run_in_executor(
                None, lambda: list(_stream_batch_results(batch_id))
            )
            for result in batch_results:
                custom_id = result.custom_id
                meta = custom_id_to_meta.get(custom_id)
                if meta is None:
                    logger.warning("Unknown custom_id in batch results: %s", custom_id)
                    continue

                listing_id = meta["listing_id"]
                result_type = result.result.type

                if result_type == "succeeded":
                    try:
                        succeeded_result = result.result
                        text = succeeded_result.message.content[0].text
                        json_content = extract_json_from_response(text)
                        extraction = pydantic.TypeAdapter(
                            FloorPlanExtraction | None
                        ).validate_json(json_content)
                        if extraction is not None and extraction.is_empty():
                            extraction = None

                        if extraction is not None:
                            logger.info(
                                "Floor plan image %d for listing %s: total=%s, breakdown=%s",
                                meta["image_idx"],
                                listing_id,
                                extraction.total,
                                extraction.breakdown,
                            )
                        else:
                            logger.info(
                                "Floor plan image %d for listing %s returned no extraction.",
                                meta["image_idx"],
                                listing_id,
                            )
                        per_image_extractions.setdefault(listing_id, []).append(
                            extraction
                        )
                    except Exception:
                        logger.exception(
                            "Failed to parse batch result for custom_id %s.", custom_id
                        )
                        per_image_extractions.setdefault(listing_id, []).append(None)

                elif result_type == "errored":
                    logger.error("Batch request %s errored.", custom_id)
                    per_image_extractions.setdefault(listing_id, []).append(None)

                elif result_type == "expired":
                    logger.error("Batch request %s expired after 24 hours.", custom_id)
                    per_image_extractions.setdefault(listing_id, []).append(None)

        else:
            context.log.info("No batch requests collected; skipping batch phase.")

        # PHASE 3: Aggregate per-listing results, update cache, build output dict.
        context.log.info("Phase 3: Building output dict...")
        output: dict[str, tuple[float | None, str | None]] = {}

        # Listings whose results came back from the batch.
        for listing_id, image_extractions in per_image_extractions.items():
            aggregated = _aggregate_floor_plan_extractions(image_extractions)
            floor_plan_cache.update([(listing_id, aggregated)])
            output[listing_id] = aggregated
            context.log.info(
                "Listing %s: aggregated extraction → total=%s, breakdown=%s",
                listing_id,
                aggregated[0],
                aggregated[1],
            )

        # Listings for which we submitted batch requests but whose custom_id
        # never appeared in the results (e.g. all images failed to download so
        # no request was submitted, or the batch silently dropped the ID).
        # These are recorded as (None, None) so Phase D knows we tried.
        for listing_id in submitted_listing_ids - output.keys():
            output[listing_id] = (None, None)
            floor_plan_cache.update([(listing_id, (None, None))])
            logger.warning(
                "Listing %s: submitted to batch but no result received — recording (None, None).",
                listing_id,
            )

        # Listings served from cache.
        output.update(cached_results)

        context.log.info(
            "Extraction complete. %d listing(s) in output dict.", len(output)
        )
        return output

    return asyncio.run(_run_all())
