"""Anthropic API configuration and utilities."""

import logging
import os
from typing import Any

import anthropic
import pydantic

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5"


def detect_image_format(image_data: bytes) -> str:
    """Detect image format from magic bytes.

    Returns MIME type (e.g., "image/jpeg", "image/png", "image/gif", "image/webp").
    Defaults to "image/jpeg" if format cannot be determined.
    """
    if len(image_data) < 4:
        return "image/jpeg"

    # Check magic bytes (file signatures)
    if image_data[:3] == b"\xff\xd8\xff":  # JPEG
        return "image/jpeg"
    elif image_data[:8] == b"\x89PNG\r\n\x1a\n":  # PNG
        return "image/png"
    elif image_data[:4] == b"GIF8":  # GIF
        return "image/gif"
    elif image_data[:4] == b"RIFF" and image_data[8:12] == b"WEBP":  # WebP
        return "image/webp"

    return "image/jpeg"  # Default fallback


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


def build_output_config(model: type[pydantic.BaseModel]) -> dict[str, Any]:
    """Build structured output config for a Pydantic model.

    Returns config compatible with Anthropic's GA structured output format.
    GA requires additionalProperties: false on all object schemas.
    """
    schema = model.model_json_schema()

    def add_additional_properties_false(obj: Any) -> None:
        """Recursively add additionalProperties: false to all objects."""
        if isinstance(obj, dict):
            if obj.get("type") == "object" and "additionalProperties" not in obj:
                obj["additionalProperties"] = False
            for value in obj.values():
                add_additional_properties_false(value)
        elif isinstance(obj, list):
            for item in obj:
                add_additional_properties_false(item)

    add_additional_properties_false(schema)
    return {
        "format": {
            "type": "json_schema",
            "schema": schema,
        }
    }
