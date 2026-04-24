import re

import pydantic
from anthropic.types.messages.batch_create_params import Request

from rightmove.anthropic_config import (
    MODEL,
    build_description_batch_request,
    get_client,
)


def _strip_html(text: str) -> str:
    """Remove HTML tags and normalise whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_json_from_response(text: str) -> str:
    """Extract JSON from response, handling markdown code blocks."""
    text = text.strip()
    # Remove markdown code block markers (```json ... ```)
    if text.startswith("```"):
        # Remove opening ``` and optional language identifier
        lines = text.split("\n", 1)
        if len(lines) > 1:
            text = lines[1]
        # Remove closing ```
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


class ExtractedPropertyInfo(pydantic.BaseModel):
    """Fields extracted from a property description by an LLM."""

    tenure_type: str | None = None
    years_remaining_on_lease: int | None = None
    annual_service_charge: float | None = None
    annual_ground_rent: float | None = None
    council_tax_band: str | None = None


class PropertyDescriptionExtractor:
    """Extracts structured property information from a listing description.

    Uses Claude with structured output to read tenure type, remaining lease years,
    service charge, ground rent, and council tax band from property descriptions.
    """

    _PROMPT = (
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

    def __init__(self) -> None:
        self._client = get_client()

    def build_batch_request(self, custom_id: str, description: str) -> Request:
        """Build a batch request for extraction (no API call).

        Args:
            custom_id: Unique ID for this request (e.g., "desc_12345")
            description: The property listing description (may contain HTML)

        Returns:
            A Request object for batch submission.
        """
        return build_description_batch_request(custom_id, description)

    async def extract(self, description: str) -> ExtractedPropertyInfo:
        """Extract structured property info from a listing description.

        Args:
            description: The property listing description (may contain HTML).

        Returns:
            An :class:`ExtractedPropertyInfo` with any fields found in the text.
            Fields not mentioned in the description will be ``None``.
        """
        clean_text = _strip_html(description)

        response = self._client.messages.create(
            model=MODEL,
            max_tokens=256,
            messages=[  # type: ignore[arg-type]
                {
                    "role": "user",
                    "content": f"{self._PROMPT}\n\nDescription:\n{clean_text}",
                }
            ],
        )

        content = response.content[0].text
        json_content = _extract_json_from_response(content)
        extracted = pydantic.TypeAdapter(ExtractedPropertyInfo).validate_json(json_content)
        return extracted
