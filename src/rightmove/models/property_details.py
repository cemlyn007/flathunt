import pydantic
import pydantic.alias_generators

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


class Floorplan(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="ignore")

    url: str
    caption: str | None = None


class Tenure(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(
        alias_generator=pydantic.alias_generators.to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    tenure_type: str | None = None
    years_remaining_on_lease: int | None = None

    @pydantic.field_validator("years_remaining_on_lease", mode="before")
    @classmethod
    def _reject_zero(cls, v: object) -> object:
        return None if v == 0 else v


class PropertyText(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="ignore")

    description: str | None = None


class PropertyDetails(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(
        alias_generator=pydantic.alias_generators.to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    id: str
    living_costs: LivingCosts
    floorplans: list[Floorplan] = []
    tenure: Tenure | None = None
    text: PropertyText | None = None

    @property
    def tenure_type(self) -> str | None:
        return self.tenure.tenure_type if self.tenure else None

    @property
    def years_remaining_on_lease(self) -> int | None:
        return self.tenure.years_remaining_on_lease if self.tenure else None

    @property
    def description(self) -> str | None:
        return self.text.description if self.text else None
