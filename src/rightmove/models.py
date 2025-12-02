from typing import Any, Optional

import pydantic
import pydantic.alias_generators

__all__ = [
    "Highlight",
    "LookupMatch",
    "LookupMatches",
    "Location",
    "PropertyImage",
    "PropertyImages",
    "ListingUpdate",
    "DisplayPrice",
    "Price",
    "BuildToRentBenefits",
    "DevelopmentContent",
    "Customer",
    "ProductLabel",
    "MatchingLozenges",
    "LozengeModel",
    "Property",
    "PropertyLocation",
]


class CamelCaseModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(
        alias_generator=pydantic.alias_generators.to_camel,
        populate_by_name=True,
        from_attributes=True,
        serialize_by_alias=True,
    )


# Lookup Models


class Highlight(CamelCaseModel):
    text: str
    highlighted: bool


class LookupMatch(CamelCaseModel):
    id: str
    type: str
    display_name: str
    highlighting: str
    highlights: list[Highlight]

    @property
    def location_identifier(self) -> str:
        return f"{self.type}^{self.id}"


class LookupMatches(CamelCaseModel):
    matches: list[LookupMatch]


# Property Models


class Location(CamelCaseModel):
    latitude: float
    longitude: float


class PropertyLocation(CamelCaseModel):
    id: int
    location: Location


class PropertyImage(CamelCaseModel):
    url: str
    caption: Optional[str] = None
    src_url: str


class PropertyImages(CamelCaseModel):
    images: list[PropertyImage]
    main_image_src: str
    main_map_image_src: str


class ListingUpdate(CamelCaseModel):
    listing_update_reason: Optional[str]
    listing_update_date: Optional[pydantic.AwareDatetime]


class DisplayPrice(CamelCaseModel):
    display_price: str
    display_price_qualifier: str


class Price(CamelCaseModel):
    amount: int
    frequency: str
    currency_code: Optional[str] = None
    display_prices: Optional[list[DisplayPrice]] = None


class BuildToRentBenefits(CamelCaseModel):
    id: int
    label: str
    icon: str
    position_on_page: int


class DevelopmentContent(CamelCaseModel):
    headline: Optional[Any] = None
    "Currently the type is not known."
    features: Optional[Any] = None
    "Currently the type is not known."


class Customer(CamelCaseModel):
    branch_id: Optional[int] = None
    brand_plus_logo_uri: Optional[str] = None
    contact_telephone: Optional[str] = None
    branch_display_name: Optional[str] = None
    branch_name: Optional[str] = None
    brand_trading_name: Optional[str] = None
    branch_landing_page_url: Optional[str] = None
    development: bool
    show_reduced_properties: Optional[bool] = None
    commercial: bool
    show_on_map: Optional[bool] = None
    enhanced_listing: Optional[bool] = None
    development_content: Optional[DevelopmentContent] = None
    build_to_rent: Optional[bool] = None
    build_to_rent_benefits: list[BuildToRentBenefits]
    brand_plus_logo_url: Optional[str] = None


class ProductLabel(CamelCaseModel):
    product_label_text: Optional[str]
    spotlight_label: bool


class MatchingLozenges(CamelCaseModel):
    type: str | None = None
    priority: int | None = None


class LozengeModel(CamelCaseModel):
    matching_lozenges: list[MatchingLozenges]


class Property(CamelCaseModel):
    id: int
    bedrooms: int
    bathrooms: Optional[int]
    number_of_images: Optional[int] = None
    number_of_floorplans: Optional[int] = None
    number_of_virtual_tours: Optional[int] = None
    summary: str
    display_address: Optional[str] = None
    country_code: Optional[str] = None
    location: Location
    property_images: Optional[PropertyImages] = None
    property_sub_type: Optional[str] = None
    listing_update: Optional[ListingUpdate] = None
    price: Optional[Price] = None
    premium_listing: Optional[bool] = None
    featured_property: Optional[bool] = None
    customer: Optional[Customer] = None
    distance: Optional[float] = None
    transaction_type: Optional[str] = None
    product_label: Optional[ProductLabel] = None
    commercial: bool
    development: bool
    residential: bool
    students: bool
    auction: bool
    fees_apply: Optional[bool] = None
    fees_apply_text: Optional[str] = None
    display_size: Optional[str] = None
    show_on_map: Optional[bool] = None
    property_url: Optional[str] = None
    contact_url: Optional[str] = None
    static_map_url: Optional[str] = None
    channel: str
    first_visible_date: Optional[pydantic.AwareDatetime] = None
    keywords: Optional[list[str]] = None
    keyword_match_type: Optional[str] = None
    saved: Optional[bool]
    hidden: Optional[bool]
    online_viewings_available: Optional[bool] = None
    lozenge_model: Optional[LozengeModel] = None
    has_brand_plus: Optional[bool] = None
    display_status: Optional[str] = None
    enquired_timestamp: Optional[str] = None
    enquiry_added_timestamp: Optional[str] = None
    enquiry_called_timestamp: Optional[str] = None
    heading: str | None = None
    is_recent: Optional[bool] = None
    enhanced_listing: Optional[bool] = None
    added_or_reduced: Optional[str] = None
    formatted_branch_name: Optional[str] = None
    formatted_distance: Optional[str] = None
    property_type_full_description: Optional[str] = None
