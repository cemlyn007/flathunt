import pydantic

from rightmove.models import Price

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
