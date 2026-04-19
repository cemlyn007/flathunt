from typing import Any

import pydantic

from rightmove.models.base import CamelCaseModel


class Location(CamelCaseModel):
    latitude: float
    longitude: float


class PropertyImage(CamelCaseModel):
    url: str
    caption: str | None = None
    src_url: str


class PropertyImages(CamelCaseModel):
    images: list[PropertyImage]
    main_image_src: str
    main_map_image_src: str


class ListingUpdate(CamelCaseModel):
    listing_update_reason: str | None = None
    listing_update_date: pydantic.AwareDatetime | None = None


class DisplayPrice(CamelCaseModel):
    display_price: str
    display_price_qualifier: str


class Price(CamelCaseModel):
    amount: int
    frequency: str
    currency_code: str | None = None
    display_prices: list[DisplayPrice] | None = None


class BuildToRentBenefits(CamelCaseModel):
    id: int
    label: str
    icon: str
    position_on_page: int


class DevelopmentContent(CamelCaseModel):
    headline: Any | None = None
    "Currently the type is not known."
    features: Any | None = None
    "Currently the type is not known."


class Customer(CamelCaseModel):
    branch_id: int | None = None
    brand_plus_logo_uri: str | None = pydantic.Field(None, alias="brandPlusLogoURI")
    contact_telephone: str | None = None
    branch_display_name: str | None = None
    branch_name: str | None = None
    brand_trading_name: str | None = None
    branch_landing_page_url: str | None = None
    development: bool
    show_reduced_properties: bool | None = None
    has_brand_plus: bool | None = None
    commercial: bool
    show_on_map: bool | None = None
    enhanced_listing: bool | None = None
    development_content: DevelopmentContent | None = None
    build_to_rent: bool | None = None
    build_to_rent_benefits: list[BuildToRentBenefits]
    brand_plus_logo_url: str | None = None
    media_server_url: str | None = None
    update_date: pydantic.AwareDatetime | None = None
    primary_brand_colour: str | None = None


class ProductLabel(CamelCaseModel):
    product_label_text: str | None = None
    spotlight_label: bool


class MatchingLozenges(CamelCaseModel):
    type: str | None = None
    priority: int | None = None


class LozengeModel(CamelCaseModel):
    matching_lozenges: list[MatchingLozenges]


class Tenure(CamelCaseModel):
    tenure_type: str | None = None


class KeyFeature(CamelCaseModel):
    order: int
    description: str
    html_description: str


class StreetView(CamelCaseModel):
    show_street_view: bool


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


class MapProperty(_PropertyBase):
    """Properties returned by the map search endpoint."""


class ListingProperty(_PropertyBase):
    """Properties returned by the listing search endpoint."""

    number_of_virtual_tours: int
    country_code: str
    distance: float | None = None
    transaction_type: str
    tenure: Tenure | None = None
    let_available_date: pydantic.AwareDatetime | None = None
    commercial_search_prominence_selected: bool = False
    product_label: ProductLabel | None = None
    commercial: bool = False
    development: bool = False
    residential: bool = False
    students: bool = False
    fees_apply: bool | None = None
    fees_apply_text: str | None = None
    show_on_map: bool | None = None
    contact_url: str | None = None
    static_map_url: str | None = None
    first_visible_date: pydantic.AwareDatetime | None = None
    tags: list[str] = pydantic.Field(default_factory=list)
    street_view: StreetView | None = None
    enquired_timestamp: pydantic.AwareDatetime | None = None
    update_date: pydantic.AwareDatetime | None = None
    enquiry_added_timestamp: pydantic.AwareDatetime | None = None
    enquiry_called_timestamp: pydantic.AwareDatetime | None = None
    reviews: Any | None = None
    key_features: list[KeyFeature] = pydantic.Field(default_factory=list)
    enhanced_listing: bool | None = None
    formatted_branch_name: str | None = None
    added_or_reduced: str | None = None
    formatted_distance: str | None = None
    heading: str | None = None
    property_type_full_description: str | None = None
    is_recent: bool | None = None
    is_rdl_property: bool | None = None
    additional_properties: list[Any] | None = None
    number_of_additional_properties: int | None = None
