from typing import Optional

import pydantic
import pydantic.alias_generators

from rightmove.models.base import CamelCaseModel


class LivingCosts(CamelCaseModel):
    council_tax_exempt: bool
    council_tax_included: bool
    annual_ground_rent: Optional[int] = None
    ground_rent_review_period_in_years: Optional[int] = None
    ground_rent_percentage_increase: Optional[float] = None
    annual_service_charge: Optional[int] = None
    council_tax_band: Optional[str] = None
    domestic_rates: Optional[float] = None


class PropertyDetails(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(
        alias_generator=pydantic.alias_generators.to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    id: str
    living_costs: LivingCosts
