"""Shared, strongly-typed Anthropic batch extraction for all pipelines.

Owns every Anthropic type, prompt, request builder, the batch runner, and the
single ``extract_attributes`` entry point. Source-agnostic: pipelines normalise
their own detail models into ``ListingExtractionInput`` at the boundary.
"""

import asyncio
import base64
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, cast

import dagster as dg
import httpx
import pydantic
from anthropic.types.message_create_params import (
    MessageCreateParamsNonStreaming,
    OutputConfigParam,
)
from anthropic.types.message_param import MessageParam
from anthropic.types.messages.batch_create_params import Request

import rightmove.models
from flathunt.cache import ModelCache
from rightmove.anthropic_config import (
    MODEL,
    build_output_config,
    detect_image_format,
    get_client,
)
from rightmove.floor_plan import (
    FloorPlanExtraction as _LegacyFloorPlanExtraction,
)
from rightmove.floor_plan import (
    FloorPlanSizeExtractor,
)

logger = logging.getLogger(__name__)

SQFT_TO_SQM = 0.09290304

FLOOR_PLAN_CACHE_TTL = 30 * 24 * 3600  # 30 days
DESCRIPTION_CACHE_TTL = 30 * 24 * 3600  # 30 days

BATCH_POLL_INITIAL_DELAY = 30  # seconds
BATCH_POLL_MAX_DELAY = 180  # seconds
BATCH_POLL_BACKOFF = 1.5


class ExtractionKind(StrEnum):
    FLOOR_PLAN = "floor_plan"
    DESCRIPTION = "description"


class FloorPlanExtraction(pydantic.BaseModel):
    total: float | None = None
    breakdown: list[float] | None = None
    units: Literal["sq m", "sq ft"] | None = None

    def is_empty(self) -> bool:
        return self.total is None and self.breakdown is None and self.units is None

    def get_total_sqm(self) -> float | None:
        if self.units is None:
            return None
        if self.total is not None:
            return self.total if self.units == "sq m" else self.total * SQFT_TO_SQM
        if self.breakdown:
            max_val = max(self.breakdown)
            return max_val if self.units == "sq m" else max_val * SQFT_TO_SQM
        return None

    def get_breakdown_csv(self) -> str | None:
        if not self.breakdown:
            return None
        if self.units == "sq m":
            return ",".join(f"{v:.1f}" for v in self.breakdown)
        return ",".join(f"{v * SQFT_TO_SQM:.1f}" for v in self.breakdown)


class FloorPlanResult(pydantic.BaseModel):
    total_sqm: float | None = None
    breakdown_csv: str | None = None


class ExtractedPropertyInfo(pydantic.BaseModel):
    tenure_type: str | None = None
    years_remaining_on_lease: int | None = None
    annual_service_charge: float | None = None
    annual_ground_rent: float | None = None
    council_tax_band: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None


class ExtractedAttributes(pydantic.BaseModel):
    floor_plan: FloorPlanResult | None = None
    description: ExtractedPropertyInfo | None = None


class RequestMeta(pydantic.BaseModel):
    kind: ExtractionKind
    listing_id: str


@dataclass(frozen=True)
class ExtractionRequest:
    meta: RequestMeta
    request: Request


class ListingExtractionInput(pydantic.BaseModel):
    listing_id: str
    description: str | None
    floor_plan_image_urls: list[str]
    needs_floor_plan: bool
    needs_description: bool


FLOOR_PLAN_PROMPT = (
    "You are shown one or more images that are all floor plan pages for a SINGLE "
    "property. Considering ALL of them together, determine the floor area(s):\n"
    "\n"
    "1. If a TOTAL floor area is clearly labeled in any image (e.g. 'Total: 93 sqm', "
    "'Gross: 100 m²'): return the total value and units.\n"
    "2. If only individual floor/room sizes are shown across the images with NO "
    "total: return a breakdown with each floor's usable internal area and units.\n"
    "3. If no size information is shown or it is too ambiguous/complex: return null "
    "for total, null for breakdown, and null for units.\n"
    "\n"
    "For usable area, exclude balconies, terraces, gardens, attics, and rooms with "
    "ceiling height below 1.5m. Prefer sq m if both units are present."
)

DESCRIPTION_PROMPT = (
    "Extract property details from this residential property listing description. "
    "Return a JSON object with these fields:\n"
    "- tenure_type: one of 'LEASEHOLD', 'FREEHOLD', 'SHARE_OF_FREEHOLD', or null\n"
    "- years_remaining_on_lease: integer years remaining, or null\n"
    "- annual_service_charge: yearly amount in GBP (number only, no currency), or null\n"
    "- annual_ground_rent: annual amount in GBP (number only, no currency), or null\n"
    "- council_tax_band: single letter A-I, or null\n"
    "- bedrooms: integer number of bedrooms, or null\n"
    "- bathrooms: integer number of bathrooms, or null\n\n"
    "If a field is not mentioned, use null. Extract only information explicitly "
    "stated in the description."
)


def calculate_backoff_delay(poll_count: int) -> int:
    """Calculate exponential backoff delay in seconds.

    Starts at 30s, increases by 1.5x each iteration, caps at 180s (5 min).
    """
    delay = int(BATCH_POLL_INITIAL_DELAY * (BATCH_POLL_BACKOFF**poll_count))
    return min(delay, BATCH_POLL_MAX_DELAY)


def build_floor_plan_request(listing_id: str, images: list[bytes]) -> ExtractionRequest:
    """Build a typed batch request for floor plan extraction across all images."""
    image_blocks: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": detect_image_format(image),
                "data": base64.b64encode(image).decode("ascii"),
            },
        }
        for image in images
    ]
    content: list[dict[str, Any]] = [{"type": "text", "text": FLOOR_PLAN_PROMPT}]
    content.extend(image_blocks)
    output_config = cast(OutputConfigParam, build_output_config(FloorPlanExtraction))
    messages = cast(list[MessageParam], [{"role": "user", "content": content}])
    request = Request(
        custom_id=f"fp_{listing_id}",
        params=MessageCreateParamsNonStreaming(
            model=MODEL, max_tokens=1024, output_config=output_config, messages=messages
        ),
    )
    return ExtractionRequest(
        meta=RequestMeta(kind=ExtractionKind.FLOOR_PLAN, listing_id=listing_id),
        request=request,
    )


def build_description_request(listing_id: str, description: str) -> ExtractionRequest:
    """Build a typed batch request for property description extraction."""
    clean = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", description)).strip()
    output_config = cast(OutputConfigParam, build_output_config(ExtractedPropertyInfo))
    messages = cast(
        list[MessageParam],
        [{"role": "user", "content": f"{DESCRIPTION_PROMPT}\n\nDescription:\n{clean}"}],
    )
    request = Request(
        custom_id=f"desc_{listing_id}",
        params=MessageCreateParamsNonStreaming(
            model=MODEL, max_tokens=256, output_config=output_config, messages=messages
        ),
    )
    return ExtractionRequest(
        meta=RequestMeta(kind=ExtractionKind.DESCRIPTION, listing_id=listing_id),
        request=request,
    )


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


def _stream_batch_results(batch_id: str) -> Iterable[Any]:
    """Seam for tests: returns the raw Anthropic batch results iterable."""
    client = get_client()
    return client.messages.batches.results(batch_id)


def _succeeded_text(result: Any) -> str:
    """The ONLY place SDK shapes leak. Everything downstream is fully typed."""
    return cast(str, result.result.message.content[0].text)


def _parse_batch_results(
    batch_id: str,
    meta_by_custom_id: dict[str, RequestMeta],
    context: dg.AssetExecutionContext,
) -> tuple[dict[str, FloorPlanResult], dict[str, ExtractedPropertyInfo]]:
    floor_plans: dict[str, FloorPlanResult] = {}
    descriptions: dict[str, ExtractedPropertyInfo] = {}

    for result in _stream_batch_results(batch_id):
        meta = meta_by_custom_id.get(result.custom_id)
        if meta is None:
            logger.warning("Unknown custom_id in batch results: %s", result.custom_id)
            continue
        if result.result.type != "succeeded":
            logger.error(
                "Batch request %s %s — not cached, will retry next run.",
                result.custom_id,
                result.result.type,
            )
            continue
        try:
            json_content = extract_json_from_response(_succeeded_text(result))
            if meta.kind is ExtractionKind.FLOOR_PLAN:
                extraction = pydantic.TypeAdapter(
                    FloorPlanExtraction | None
                ).validate_json(json_content)
                if extraction is None or extraction.is_empty():
                    floor_plans[meta.listing_id] = FloorPlanResult()
                else:
                    floor_plans[meta.listing_id] = FloorPlanResult(
                        total_sqm=extraction.get_total_sqm(),
                        breakdown_csv=extraction.get_breakdown_csv(),
                    )
            else:
                descriptions[meta.listing_id] = pydantic.TypeAdapter(
                    ExtractedPropertyInfo
                ).validate_json(json_content)
        except (ValueError, pydantic.ValidationError):
            logger.exception(
                "Failed to parse %s result for %s.", meta.kind, result.custom_id
            )
    return floor_plans, descriptions


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


_LLM_CALL_INTERVAL = 0.5  # seconds between LLM calls


async def _extract_all_floor_plans(
    prop_id: int,
    details: rightmove.models.PropertyDetails | None,
    extractor: FloorPlanSizeExtractor,
    llm_semaphore: asyncio.Semaphore,
) -> _LegacyFloorPlanExtraction | None:
    """Extract sizes from all floor plan images, aggregating results intelligently.

    - Prefers total size if found in any image
    - Falls back to breakdown (per-floor) if only breakdowns are available
    - Returns None if ambiguous or no sizes found
    """
    if details is None or not details.floorplans:
        logger.warning("Property %d has no floor plan URLs in page model.", prop_id)
        return None

    all_extractions: list[_LegacyFloorPlanExtraction] = []

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
