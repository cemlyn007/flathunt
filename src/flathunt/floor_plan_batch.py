"""Shared Anthropic-batch infrastructure for floor-plan (and other) pipelines.

Provides constants, backoff helpers, batch submission/polling, JSON extraction,
and a floor-plan result parser that can be reused across any pipeline that submits
Anthropic message batches.
"""

import asyncio
import logging

import dagster as dg
import httpx
import pydantic
from anthropic.types.messages.batch_create_params import Request

import rightmove.models
from flathunt.cache import ModelCache
from rightmove.anthropic_config import get_client
from rightmove.floor_plan import FloorPlanExtraction, FloorPlanSizeExtractor

logger = logging.getLogger(__name__)

_LLM_CALL_INTERVAL = 0.5  # seconds between LLM calls

BATCH_POLL_INITIAL_DELAY = 30  # seconds
BATCH_POLL_MAX_DELAY = 180  # seconds
BATCH_POLL_BACKOFF = 1.5  # multiplier for exponential backoff


def calculate_backoff_delay(poll_count: int) -> int:
    """Calculate exponential backoff delay in seconds.

    Starts at 30s, increases by 1.5x each iteration, caps at 180s (5 min).
    """
    delay = int(BATCH_POLL_INITIAL_DELAY * (BATCH_POLL_BACKOFF**poll_count))
    return min(delay, BATCH_POLL_MAX_DELAY)


def submit_batch(
    requests: list[Request],
    context: dg.AssetExecutionContext,
) -> str:
    """Submit batch to Anthropic and return batch_id."""
    client = get_client()
    batch = client.messages.batches.create(requests=requests)
    context.log.info(
        "Submitted batch %s with %d requests. Will expire at %s",
        batch.id,
        len(requests),
        batch.expires_at,
    )
    return batch.id


async def poll_batch_completion(
    batch_id: str,
    context: dg.AssetExecutionContext,
) -> None:
    """Poll batch until completion, using exponential backoff."""
    client = get_client()
    poll_count = 0

    while True:
        batch = client.messages.batches.retrieve(batch_id)

        if batch.processing_status == "ended":
            context.log.info(
                "Batch %s completed. Results: succeeded=%d, errored=%d, "
                "expired=%d, canceled=%d",
                batch_id,
                batch.request_counts.succeeded,
                batch.request_counts.errored,
                batch.request_counts.expired,
                batch.request_counts.canceled,
            )
            break

        delay = calculate_backoff_delay(poll_count)
        context.log.info(
            "Batch %s still processing (%d remaining)... waiting %ds",
            batch_id,
            batch.request_counts.processing,
            delay,
        )
        await asyncio.sleep(delay)
        poll_count += 1


def extract_json_from_response(text: str) -> str:
    """Extract JSON from response, handling markdown code blocks."""
    text = text.strip()
    # Remove markdown code block markers (```json ... ```)
    if text.startswith("```"):
        # Remove opening ``` and optional language identifier
        lines = text.split("\n", 1)
        if len(lines) > 1:
            text = lines[1]
        # Remove closing ```
        text = text.removesuffix("```")
    return text.strip()


def parse_floor_plan_result(
    json_content: str,
) -> tuple[float | None, str | None]:
    """Parse a floor-plan extraction JSON response into (total_sqm, breakdown_csv).

    Returns (None, None) if the extraction is empty or returned no data.
    Raises ValueError / pydantic.ValidationError on parse failure (caller logs).
    """
    extraction = pydantic.TypeAdapter(FloorPlanExtraction | None).validate_json(
        json_content
    )
    if extraction is None or extraction.is_empty():
        return (None, None)
    return extraction.get_total_sqm(), extraction.get_breakdown_csv()


async def _extract_all_floor_plans(
    prop_id: int,
    details: rightmove.models.PropertyDetails | None,
    extractor: FloorPlanSizeExtractor,
    llm_semaphore: asyncio.Semaphore,
) -> FloorPlanExtraction | None:
    """Extract sizes from all floor plan images, aggregating results intelligently.

    - Prefers total size if found in any image
    - Falls back to breakdown (per-floor) if only breakdowns are available
    - Returns None if ambiguous or no sizes found
    """
    if details is None or not details.floorplans:
        logger.warning("Property %d has no floor plan URLs in page model.", prop_id)
        return None

    all_extractions: list[FloorPlanExtraction] = []

    for i, floor_plan in enumerate(details.floorplans):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(floor_plan.url, timeout=30.0)
                response.raise_for_status()

            async with llm_semaphore:
                extraction = await extractor.extract(response.content)
                await asyncio.sleep(_LLM_CALL_INTERVAL)

            if extraction is not None:
                all_extractions.append(extraction)
                logger.info(
                    "Extracted floor plan %d for property %d: total=%s, breakdown=%s",
                    i,
                    prop_id,
                    extraction.total,
                    extraction.breakdown,
                )
        except Exception:
            logger.exception(
                "Failed to extract floor plan %d for property %d — continuing.",
                i,
                prop_id,
            )

    if not all_extractions:
        logger.info("No floor plan sizes extracted for property %d.", prop_id)
        return None

    # Aggregate: prefer total over breakdown
    for extraction in all_extractions:
        if extraction.total is not None:
            logger.info(
                "Using total size %.1f %s for property %d from %d floor plans.",
                extraction.total,
                extraction.units,
                prop_id,
                len(all_extractions),
            )
            return extraction

    # If no total found, use first extraction's breakdown
    return all_extractions[0]


async def get_floor_plan_sqm(
    prop_id: int,
    details: rightmove.models.PropertyDetails | None,
    cache: ModelCache[tuple[float | None, str | None]],
    extractor: FloorPlanSizeExtractor,
    llm_semaphore: asyncio.Semaphore,
) -> tuple[float | None, str | None]:
    """Return (total_sqm, breakdown_csv) using cache or LLM extraction.

    Only writes to the cache on a successful extraction attempt so that
    transient failures (network errors, rate limits) are retried on the
    next run rather than being permanently recorded as missing.
    """
    cache_key = str(prop_id)
    try:
        return cache.get(cache_key)
    except KeyError:
        pass

    total_sqm: float | None = None
    breakdown_csv: str | None = None

    try:
        extraction = await _extract_all_floor_plans(
            prop_id, details, extractor, llm_semaphore
        )
        if extraction is not None:
            total_sqm = extraction.get_total_sqm()
            breakdown_csv = extraction.get_breakdown_csv()

        cache.update([(cache_key, (total_sqm, breakdown_csv))])
    except Exception:
        logger.exception(
            "Failed to extract floor plan size for property %d — keeping property.",
            prop_id,
        )

    return (total_sqm, breakdown_csv)
