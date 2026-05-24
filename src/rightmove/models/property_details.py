import pydantic
import pydantic.alias_generators

from rightmove.models._detail_tenure import Tenure
from rightmove.models.floorplan import Floorplan
from rightmove.models.living_costs import LivingCosts
from rightmove.models.property_text import PropertyText


class _DetailLocation(pydantic.BaseModel):
    """Lat/lon from the property detail page; ignores extra fields like zoomLevel."""

    model_config = pydantic.ConfigDict(
        alias_generator=pydantic.alias_generators.to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    latitude: float
    longitude: float


class _Sizing(pydantic.BaseModel):
    """A single size measurement from the detail page's ``sizings`` array."""

    model_config = pydantic.ConfigDict(
        alias_generator=pydantic.alias_generators.to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    unit: str
    display_unit: str | None = None
    minimum_size: float | None = None
    maximum_size: float | None = None


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
    location: _DetailLocation | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    sizings: list[_Sizing] = []

    @property
    def tenure_type(self) -> str | None:
        return self.tenure.tenure_type if self.tenure else None

    @property
    def years_remaining_on_lease(self) -> int | None:
        return self.tenure.years_remaining_on_lease if self.tenure else None

    @property
    def description(self) -> str | None:
        return self.text.description if self.text else None

    @property
    def size_sqm(self) -> float | None:
        """Return the floor area in square metres from ``sizings``, if present."""
        for sizing in self.sizings:
            if sizing.unit == "sqm":
                return sizing.minimum_size
        return None
