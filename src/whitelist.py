"""Vulture whitelist — symbols defined now but used in later tasks."""

from flathunt.anthropic_extraction import (
    ExtractedAttributes,
    ListingExtractionInput,
    build_description_request,
    build_floor_plan_request,
)

_ = ExtractedAttributes
_ = ListingExtractionInput
_ = build_description_request
_ = build_floor_plan_request
