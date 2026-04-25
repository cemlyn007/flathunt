import pydantic
import pydantic.alias_generators

from rightmove.models._detail_tenure import Tenure
from rightmove.models.floorplan import Floorplan
from rightmove.models.living_costs import LivingCosts
from rightmove.models.property_text import PropertyText


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
