import base64
import logging
import os
from typing import Literal

import httpx
import pydantic

logger = logging.getLogger(__name__)


_SQFT_TO_SQM = 0.09290304


class FloorPlanSize(pydantic.BaseModel):
    value: float
    units: Literal["sq m", "sq ft"]

    def to_sqm(self) -> float:
        if self.units == "sq m":
            return self.value
        return self.value * _SQFT_TO_SQM


class FloorPlanSizeExtractor:
    """Extracts floor plan size from an image by querying the GitHub Models API.

    Uses the OpenAI-compatible GitHub Models chat completions endpoint with
    vision support to read the size annotation written on a floor plan image.

    Args:
        token: GitHub personal access token. Defaults to the ``GITHUB_TOKEN``
            environment variable.
        model: The model to use. Defaults to ``"gpt-4o-mini"``.
    """

    _API_URL = "https://models.inference.ai.azure.com/chat/completions"

    _PROMPT = (
        "This is a floor plan image. If a total floor area size is written "
        "anywhere in the image, extract it and respond with exactly two lines:\n"
        "LINE1: the numeric value only (e.g. 93.0)\n"
        "LINE2: the units only, using exactly one of these literals: sq m, sq ft\n"
        "If both sq m and sq ft are present, prefer sq m.\n"
        "If multiple sizes are shown (e.g. per room or per floor), prefer the one "
        "that represents the usable internal floor area, excluding outdoor areas "
        "such as balconies, terraces, and gardens, and also excluding attics and "
        "any rooms with a ceiling height below 1.5 metres.\n"
        "If no size is written in the image, respond with exactly: NOT_FOUND"
    )

    def __init__(
        self,
        token: str | None = None,
        model: str = "gpt-4o-mini",
    ) -> None:
        self._token = token or os.environ["GITHUB_TOKEN"]
        self._model = model

    async def extract(
        self,
        image_data: bytes,
        media_type: str = "image/jpeg",
    ) -> FloorPlanSize | None:
        """Extract the floor plan size printed in the image.

        Args:
            image_data: Raw bytes of the floor plan image.
            media_type: MIME type of the image (e.g. ``"image/jpeg"``).

        Returns:
            A :class:`FloorPlanSize` with ``value`` and ``units``, or ``None``
            if no size annotation was found.
        """
        encoded = base64.b64encode(image_data).decode("ascii")
        data_url = f"data:{media_type};base64,{encoded}"

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                }
            ],
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._API_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                timeout=60.0,
            )
            response.raise_for_status()

        text = response.json()["choices"][0]["message"]["content"].strip()
        if "NOT_FOUND" in text:
            return None

        lines = [
            line.split(":", 1)[-1].strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("```")
        ]
        try:
            return FloorPlanSize(value=float(lines[0]), units=lines[1])
        except (ValueError, IndexError, pydantic.ValidationError):
            logger.error("Failed to parse floor plan size from LLM output: %r", text)
            raise
