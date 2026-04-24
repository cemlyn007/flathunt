import base64
import logging
from typing import Literal

import pydantic
from anthropic.types.messages.batch_create_params import Request

from rightmove.anthropic_config import (
    MODEL,
    build_floor_plan_batch_request,
    build_output_config,
    detect_image_format,
    get_client,
)

logger = logging.getLogger(__name__)


_SQFT_TO_SQM = 0.09290304


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
        text = text.removesuffix("```")
    return text.strip()


class FloorPlanSize(pydantic.BaseModel):
    value: float
    units: Literal["sq m", "sq ft"]

    def to_sqm(self) -> float:
        if self.units == "sq m":
            return self.value
        return self.value * _SQFT_TO_SQM


class FloorPlanExtraction(pydantic.BaseModel):
    total: float | None = None
    breakdown: list[float] | None = None
    units: Literal["sq m", "sq ft"]

    def get_total_sqm(self) -> float | None:
        """Return total in square metres, or largest breakdown value if no total."""
        if self.total is not None:
            return self.total if self.units == "sq m" else self.total * _SQFT_TO_SQM
        if self.breakdown:
            max_val = max(self.breakdown)
            return max_val if self.units == "sq m" else max_val * _SQFT_TO_SQM
        return None

    def get_breakdown_csv(self) -> str | None:
        """Return breakdown as comma-separated string, converted to sqm."""
        if not self.breakdown:
            return None
        if self.units == "sq m":
            return ",".join(f"{v:.1f}" for v in self.breakdown)
        return ",".join(f"{v * _SQFT_TO_SQM:.1f}" for v in self.breakdown)


class FloorPlanSizeExtractor:
    """Extracts floor plan sizes from an image using Claude with structured output.

    Uses Anthropic's API with vision capabilities and structured output to
    intelligently detect total floor area or per-floor breakdown.
    """

    _PROMPT = (
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

    def __init__(self) -> None:
        self._client = get_client()

    def build_batch_request(
        self,
        custom_id: str,
        image_data: bytes,
        media_type: str | None = None,
    ) -> Request:
        """Build a batch request for extraction (no API call).

        Args:
            custom_id: Unique ID for this request (e.g., "fp_12345_0")
            image_data: Raw bytes of the floor plan image
            media_type: MIME type of the image (auto-detected if not provided)

        Returns:
            A Request object for batch submission.
        """
        return build_floor_plan_batch_request(custom_id, image_data, media_type)

    async def extract(
        self,
        image_data: bytes,
        media_type: str | None = None,
    ) -> FloorPlanExtraction | None:
        """Extract floor plan sizes from the image using Claude.

        Intelligently handles different formats:
        - Total size if clearly labeled
        - Per-floor breakdown if only individual sizes are shown
        - None if ambiguous or not found

        Args:
            image_data: Raw bytes of the floor plan image.
            media_type: MIME type of the image (auto-detected if not provided).

        Returns:
            A :class:`FloorPlanExtraction` with total and/or breakdown, or ``None``
            if no size annotation was found or image is ambiguous.
        """
        if media_type is None:
            media_type = detect_image_format(image_data)

        encoded = base64.b64encode(image_data).decode("ascii")

        response = self._client.messages.create(  # type: ignore
            model=MODEL,
            max_tokens=1024,
            output_config=build_output_config(FloorPlanExtraction),
            messages=[  # type: ignore
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": self._PROMPT,
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
        )

        try:
            content = response.content[0].text
            json_content = _extract_json_from_response(content)
            extraction_dict = pydantic.TypeAdapter(
                FloorPlanExtraction | None
            ).validate_json(json_content)
            return extraction_dict
        except (ValueError, pydantic.ValidationError) as e:
            logger.error("Failed to parse floor plan extraction: %s", e)
            return None
