import pydantic

from rightmove.models.base import CamelCaseModel


class ListingUpdate(CamelCaseModel):
    listing_update_reason: str | None = None
    listing_update_date: pydantic.AwareDatetime | None = None
