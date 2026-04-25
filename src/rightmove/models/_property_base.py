import pydantic

from rightmove.models.base import CamelCaseModel
from rightmove.models.customer import Customer
from rightmove.models.listing_update import ListingUpdate
from rightmove.models.location import Location
from rightmove.models.lozenge_model import LozengeModel
from rightmove.models.price import Price
from rightmove.models.property_image import PropertyImage
from rightmove.models.property_images import PropertyImages


class _PropertyBase(CamelCaseModel):
    """Shared fields between map and listing search responses."""

    id: int
    location: Location
    bedrooms: int | None = None
    bathrooms: int | None = None
    number_of_images: int
    number_of_floorplans: int
    summary: str
    display_address: str
    images: list[PropertyImage]
    property_images: PropertyImages
    property_sub_type: str | None = None
    listing_update: ListingUpdate | None = None
    price: Price
    premium_listing: bool
    featured_property: bool
    customer: Customer
    auction: bool
    display_size: str | None = None
    property_url: str
    channel: str
    saved: bool
    online_viewings_available: bool
    lozenge_model: LozengeModel
    keywords: list[str] = pydantic.Field(default_factory=list)
    keyword_match_type: str | None = None
    hidden: bool = False
    has_brand_plus: bool | None = None
    display_status: str | None = None
