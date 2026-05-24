"""Vulture whitelist — symbols defined now but used in later tasks."""

from flathunt.anthropic_extraction import (
    extract_attributes,
    get_floor_plan_sqm,
    parse_floor_plan_result,
)
from rightmove.description_extractor import PropertyDescriptionExtractor

_ = extract_attributes
_ = get_floor_plan_sqm
_ = parse_floor_plan_result
_ = PropertyDescriptionExtractor
