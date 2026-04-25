import pydantic

from rightmove.floor_plan import _SQFT_TO_SQM
from rightmove.models import Price

# ============================================================================
# Utility Functions
# ============================================================================


def parse_display_size_sqm(display_size: str | None) -> float | None:
    """Parse a Rightmove display_size field to square meters.

    Handles both square feet and square metres display formats as used by
    Rightmove properties. Properties with no size information return None.

    Args:
        display_size: The display_size field from a Rightmove property, e.g.
            "1,234 sq. ft." or "115 sqm". May be None.

    Returns:
        The property size in square metres, or None if not available.
    """
    if not display_size:
        return None

    if display_size.endswith(" sq. ft."):
        try:
            square_ft = int(display_size.removesuffix(" sq. ft.").replace(",", ""))
            return float(int(square_ft * _SQFT_TO_SQM))
        except (ValueError, AttributeError):
            return None
    elif display_size.endswith(" sqm"):
        try:
            return float(int(display_size.removesuffix(" sqm").replace(",", "")))
        except (ValueError, AttributeError):
            return None

    return None


# ============================================================================
# Simple/Intermediate Models
# ============================================================================


class MatchedProperty(pydantic.BaseModel):
    """A property that passed the commute filter, with its per-destination durations."""

    property_id: int
    commute_durations: list[int | None]


# ============================================================================
# Complete/Enriched Models
# ============================================================================


class FinalProperty(pydantic.BaseModel):
    """A fully enriched property that passed all filters.

    Combines property details from Rightmove with extracted/enriched data
    and commute information to provide a complete view of a property.
    """

    # Core property information
    id: int
    display_address: str
    property_url: str | None = None

    # Basic property features
    bedrooms: int | None = None
    bathrooms: int | None = None

    # Size information
    display_size: str | None = None
    extracted_sqm: float | None = None
    extracted_sqm_breakdown: str | None = None

    # Price information
    price: Price | None = None

    # Commute data
    commute_durations: list[int | None] = []

    # Council tax and ground rent information
    council_tax_band: str | None = None
    annual_ground_rent: float | None = None
    ground_rent_review_period_in_years: int | None = None
    ground_rent_percentage_increase: float | None = None
    extracted_council_tax_band: str | None = None
    extracted_annual_ground_rent: float | None = None

    # Service charge information
    annual_service_charge: float | None = None
    extracted_annual_service_charge: float | None = None

    # Tenure and lease information
    tenure_type: str | None = None
    years_remaining_on_lease: int | None = None
    extracted_tenure_type: str | None = None
    extracted_years_remaining_on_lease: int | None = None
