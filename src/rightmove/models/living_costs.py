from rightmove.models.base import CamelCaseModel


class LivingCosts(CamelCaseModel):
    council_tax_exempt: bool
    council_tax_included: bool
    annual_ground_rent: float | None = None
    ground_rent_review_period_in_years: int | None = None
    ground_rent_percentage_increase: float | None = None
    annual_service_charge: float | None = None
    council_tax_band: str | None = None
    domestic_rates: float | None = None
