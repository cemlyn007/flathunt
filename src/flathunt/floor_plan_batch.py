"""Shared Anthropic-batch infrastructure for floor-plan (and other) pipelines.

Provides constants, backoff helpers, batch submission/polling, JSON extraction,
and a floor-plan result parser that can be reused across any pipeline that submits
Anthropic message batches.
"""

import asyncio
import logging

import dagster as dg
import pydantic
from anthropic.types.messages.batch_create_params import Request

from rightmove.anthropic_config import get_client
from rightmove.floor_plan import FloorPlanExtraction

logger = logging.getLogger(__name__)

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
