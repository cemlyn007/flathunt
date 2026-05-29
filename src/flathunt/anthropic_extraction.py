"""Shared, strongly-typed Anthropic batch extraction for all pipelines.

Owns every Anthropic type, prompt, request builder, the batch runner, and the
single ``extract_attributes`` entry point. Source-agnostic: pipelines normalise
their own detail models into ``ListingExtractionInput`` at the boundary.
"""

import asyncio
import base64
import logging
import re
from collections.abc import Iterator
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

from flathunt.cache import ModelCache
from rightmove.anthropic_config import (
    MODEL,
    build_output_config,
    detect_image_format,
    get_client,
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
    below_ground: bool | None = None

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
    below_ground: bool | None = None


class ExtractedPropertyInfo(pydantic.BaseModel):
    tenure_type: str | None = None
    years_remaining_on_lease: int | None = None
    annual_service_charge: float | None = None
    annual_ground_rent: float | None = None
    council_tax_band: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    below_ground: bool | None = None


class ExtractedAttributes(pydantic.BaseModel):
    floor_plan: FloorPlanResult | None = None
    description: ExtractedPropertyInfo | None = None

    def is_below_ground(self) -> bool | None:
        """Reconcile the floor-plan and description below-ground signals.

        Conservative agreement: ``True`` only when at least one source says
        below-ground and neither contradicts it; ``False`` only when at least
        one says above-ground and neither says below-ground; ``None`` when both
        are unknown or the two sources directly conflict.
        """
        signals = [
            self.floor_plan.below_ground if self.floor_plan else None,
            self.description.below_ground if self.description else None,
        ]
        has_true = any(s is True for s in signals)
        has_false = any(s is False for s in signals)
        if has_true and not has_false:
            return True
        if has_false and not has_true:
            return False
        return None


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
    "\n\n"
    "Separately, set below_ground based on the property's MAIN living space:\n"
    "- true ONLY if the entire or main living area is on a lower-ground or "
    "basement floor (e.g. every habitable room is labelled 'Lower Ground Floor' "
    "or 'Basement').\n"
    "- false if the main living area is at or above ground level, including "
    "split-level layouts spanning a ground floor and a lower floor, or a house "
    "that merely includes a basement room.\n"
    "- null if the floor level cannot be determined from the plan(s)."
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
    "- bathrooms: integer number of bathrooms, or null\n"
    "- below_ground: true ONLY if the main/entire living area is below street "
    "level (a lower-ground floor flat or basement flat); false if at or above "
    "ground level (including split-level homes spanning ground and a lower "
    "floor, or a house that merely has a basement room); null if not "
    "determinable from the text\n\n"
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


def _stream_batch_results(batch_id: str) -> Iterator[Any]:
    """Seam for tests: yields raw Anthropic batch results.

    MUST be a generator (``yield from``), not a function that returns the SDK
    iterator. The SDK's ``JSONLDecoder`` holds the streaming ``httpx.Response``
    but NOT the ``Anthropic`` client. ``SyncHttpxClientWrapper.__del__`` closes
    the underlying socket when the client is GC'd, so if ``client`` falls out
    of scope while the iterator is still being consumed, the next stream read
    fails with ``httpx.ReadError: [Errno 9] Bad file descriptor``. Capturing
    ``client`` in the generator frame keeps it alive for the whole iteration.
    See ``TestStreamBatchResultsKeepsClientAlive`` for the regression test.
    """
    client = get_client()
    yield from client.messages.batches.results(batch_id)


def _succeeded_text(result: Any) -> str:
    """Pull the text payload off an untyped Anthropic succeeded result (SDK-shape boundary)."""
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
                if extraction is None:
                    floor_plans[meta.listing_id] = FloorPlanResult()
                elif extraction.is_empty():
                    # No area data, but below_ground may still be present — carry it.
                    floor_plans[meta.listing_id] = FloorPlanResult(
                        below_ground=extraction.below_ground
                    )
                else:
                    floor_plans[meta.listing_id] = FloorPlanResult(
                        total_sqm=extraction.get_total_sqm(),
                        breakdown_csv=extraction.get_breakdown_csv(),
                        below_ground=extraction.below_ground,
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


async def _download_images(urls: list[str]) -> list[bytes]:
    images: list[bytes] = []
    for url in urls:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()
            images.append(response.content)
        except Exception:
            logger.exception("Failed to download floor plan image %s — skipping.", url)
    return images


async def extract_attributes(
    inputs: list[ListingExtractionInput],
    floor_plan_cache: ModelCache[FloorPlanResult],
    description_cache: ModelCache[ExtractedPropertyInfo],
    context: dg.AssetExecutionContext,
) -> dict[str, ExtractedAttributes]:
    results: dict[str, ExtractedAttributes] = {}
    fp_misses: list[ListingExtractionInput] = []
    desc_misses: list[ListingExtractionInput] = []

    # Phase 0: cache resolve
    for inp in inputs:
        bundle = results.setdefault(inp.listing_id, ExtractedAttributes())
        if inp.needs_floor_plan and inp.floor_plan_image_urls:
            try:
                bundle.floor_plan = floor_plan_cache.get(inp.listing_id)
            except KeyError:
                fp_misses.append(inp)
        if inp.needs_description and inp.description:
            try:
                bundle.description = description_cache.get(inp.listing_id)
            except KeyError:
                desc_misses.append(inp)

    # Phase 1: collect requests
    requests: list[ExtractionRequest] = []
    for inp in fp_misses:
        images = await _download_images(inp.floor_plan_image_urls)
        if images:
            requests.append(build_floor_plan_request(inp.listing_id, images))
    requests.extend(
        build_description_request(inp.listing_id, inp.description)
        for inp in desc_misses
        if inp.description
    )

    if not requests:
        context.log.info("No extraction requests collected; skipping batch phase.")
        return results

    # Phase 2: run batch
    meta_by_custom_id: dict[str, RequestMeta] = {
        r.request["custom_id"]: r.meta for r in requests
    }
    batch_id = submit_batch([r.request for r in requests], context)
    await poll_batch_completion(batch_id, context)
    loop = asyncio.get_running_loop()
    floor_plans, descriptions = await loop.run_in_executor(
        None, lambda: _parse_batch_results(batch_id, meta_by_custom_id, context)
    )

    # Phase 3: cache writes + merge
    if floor_plans:
        floor_plan_cache.update(list(floor_plans.items()))
    if descriptions:
        description_cache.update(list(descriptions.items()))
    for listing_id, fp in floor_plans.items():
        results.setdefault(listing_id, ExtractedAttributes()).floor_plan = fp
    for listing_id, desc in descriptions.items():
        results.setdefault(listing_id, ExtractedAttributes()).description = desc

    return results
