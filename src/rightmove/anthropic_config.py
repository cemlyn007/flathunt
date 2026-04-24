"""Anthropic API configuration and utilities."""

import base64
import logging
import os
import re

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20241022"


def get_client() -> anthropic.Anthropic:
    """Get Anthropic API client.

    Reads API key from ANTHROPIC_API_KEY environment variable.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Please set it to your Anthropic API key."
        )
    return anthropic.Anthropic(api_key=api_key)


def build_floor_plan_batch_request(
    custom_id: str,
    image_data: bytes,
    media_type: str = "image/jpeg",
) -> Request:
    """Build a batch request for floor plan size extraction.

    Args:
        custom_id: Unique ID for this request (e.g., "fp_12345_0")
        image_data: Raw bytes of the floor plan image
        media_type: MIME type of the image (default: "image/jpeg")

    Returns:
        A Request object suitable for batch submission.
    """

    prompt = (
        "Analyze this floor plan image. Determine the floor area(s) shown:\n"
        "\n"
        "1. If there is a TOTAL floor area size clearly labeled anywhere in the image "
        "(e.g., 'Total: 93 sqm', 'Gross: 100 m²'): "
        "Return the total value and units.\n"
        "\n"
        "2. If there are ONLY individual floor/room sizes shown (e.g., floor 1: 45m², "
        "floor 2: 47m², floor 3: 33m²) with NO total: "
        "Return a breakdown with each floor's usable internal area.\n"
        "\n"
        "3. If the image shows no size information or is too ambiguous/complex: "
        "Return null.\n"
        "\n"
        "For usable area, exclude balconies, terraces, gardens, attics, and rooms "
        "with ceiling height below 1.5m. Prefer sq m if both units are present."
    )

    encoded = base64.b64encode(image_data).decode("ascii")

    return Request(
        custom_id=custom_id,
        params=MessageCreateParamsNonStreaming(
            model=MODEL,
            max_tokens=1024,
            messages=[  # type: ignore[arg-type]
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt,
                        },
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": encoded,
                            },
                        },
                    ],
                }
            ],
        ),
    )


def build_description_batch_request(
    custom_id: str,
    description: str,
) -> Request:
    """Build a batch request for property description extraction.

    Args:
        custom_id: Unique ID for this request (e.g., "desc_12345")
        description: The property listing description (may contain HTML)

    Returns:
        A Request object suitable for batch submission.
    """

    def _strip_html(text: str) -> str:
        """Remove HTML tags and normalise whitespace."""
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    prompt = (
        "Extract property details from this residential property listing description. "
        "Return a JSON object with these fields:\n"
        "- tenure_type: one of 'LEASEHOLD', 'FREEHOLD', 'SHARE_OF_FREEHOLD', or null\n"
        "- years_remaining_on_lease: integer years remaining, or null\n"
        "- annual_service_charge: yearly amount in GBP (number only, no currency), or null\n"
        "- annual_ground_rent: annual amount in GBP (number only, no currency), or null\n"
        "- council_tax_band: single letter A-I, or null\n\n"
        "If a field is not mentioned, use null. Extract only information explicitly "
        "stated in the description."
    )

    clean_text = _strip_html(description)

    return Request(
        custom_id=custom_id,
        params=MessageCreateParamsNonStreaming(
            model=MODEL,
            max_tokens=256,
            messages=[  # type: ignore[arg-type]
                {
                    "role": "user",
                    "content": f"{prompt}\n\nDescription:\n{clean_text}",
                }
            ],
        ),
    )
