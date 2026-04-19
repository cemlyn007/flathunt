import json
import os
import re

import httpx
import pydantic


def _strip_html(text: str) -> str:
    """Remove HTML tags and normalise whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
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

    Uses the OpenAI-compatible GitHub Models chat completions endpoint to read
    tenure type, remaining lease years, service charge, ground rent, and council
    tax band from the free-text description of a property.

    Args:
        token: GitHub personal access token. Defaults to the ``GITHUB_TOKEN``
            environment variable.
        model: The model to use. Defaults to ``"gpt-4o-mini"``.
    """

    _API_URL = "https://models.inference.ai.azure.com/chat/completions"

    _PROMPT = (
        "You will be given the text description of a residential property listing. "
        "Extract the following fields if they are mentioned in the description and "
        "return them as a JSON object with exactly these keys:\n"
        '- tenure_type: string, one of "LEASEHOLD", "FREEHOLD", "SHARE_OF_FREEHOLD", or null\n'
        "- years_remaining_on_lease: integer number of years remaining on the lease, or null\n"
        "- annual_service_charge: yearly service charge amount in GBP as a number (no currency symbol), or null\n"
        "- annual_ground_rent: annual ground rent amount in GBP as a number (no currency symbol), or null\n"
        "- council_tax_band: single letter A through I, or null\n\n"
        "If a field is not mentioned or cannot be determined, use null. "
        "Respond with only the JSON object and nothing else."
    )

    def __init__(
        self,
        token: str | None = None,
        model: str = "gpt-4o-mini",
    ) -> None:
        self._token = token or os.environ["GITHUB_TOKEN"]
        self._model = model

    async def extract(self, description: str) -> ExtractedPropertyInfo:
        """Extract structured property info from a listing description.

        Args:
            description: The property listing description (may contain HTML).

        Returns:
            An :class:`ExtractedPropertyInfo` with any fields found in the text.
            Fields not mentioned in the description will be ``None``.
        """
        clean_text = _strip_html(description)

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": f"{self._PROMPT}\n\nProperty description:\n{clean_text}",
                }
            ],
            "response_format": {"type": "json_object"},
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
        return ExtractedPropertyInfo.model_validate(json.loads(text))
