import pydantic

from rightmove.models import Price


class MatchedProperty(pydantic.BaseModel):
    """A property that passed the commute filter, with its per-destination durations."""

    property_id: int
    commute_durations: list[int | None]


class FinalProperty(pydantic.BaseModel):
    """A fully enriched property that passed all filters."""

    id: int
    display_address: str
    price: Price | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    display_size: str | None = None
    extracted_sqm: float | None = None
    extracted_sqm_breakdown: str | None = None
    property_url: str | None = None
    commute_durations: list[int | None] = []
    # From PropertyDetails.living_costs
    council_tax_band: str | None = None
    annual_ground_rent: float | None = None
    ground_rent_review_period_in_years: int | None = None
    ground_rent_percentage_increase: float | None = None
    annual_service_charge: float | None = None
    tenure_type: str | None = None
    years_remaining_on_lease: int | None = None
    extracted_years_remaining_on_lease: int | None = None
    extracted_tenure_type: str | None = None
    extracted_annual_service_charge: float | None = None
    extracted_annual_ground_rent: float | None = None
    extracted_council_tax_band: str | None = None
