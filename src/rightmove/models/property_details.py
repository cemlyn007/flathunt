from typing import Optional

import pydantic
import pydantic.alias_generators

from rightmove.models.base import CamelCaseModel


class LivingCosts(CamelCaseModel):
    council_tax_exempt: bool
    council_tax_included: bool
    annual_ground_rent: Optional[float] = None
    ground_rent_review_period_in_years: Optional[int] = None
    ground_rent_percentage_increase: Optional[float] = None
    annual_service_charge: Optional[float] = None
    council_tax_band: Optional[str] = None
    domestic_rates: Optional[float] = None


class Floorplan(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="ignore")

    url: str
    caption: Optional[str] = None


class Tenure(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(
        alias_generator=pydantic.alias_generators.to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    tenure_type: Optional[str] = None
    years_remaining_on_lease: Optional[int] = None


class PropertyDetails(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(
        alias_generator=pydantic.alias_generators.to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    id: str
    living_costs: LivingCosts
    floorplans: list[Floorplan] = []
    tenure: Optional[Tenure] = None

    @property
    def tenure_type(self) -> Optional[str]:
        return self.tenure.tenure_type if self.tenure else None

    @property
    def years_remaining_on_lease(self) -> Optional[int]:
        return self.tenure.years_remaining_on_lease if self.tenure else None
