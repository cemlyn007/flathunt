from typing import Any, Optional

import pydantic

from rightmove.models.base import CamelCaseModel


class Location(CamelCaseModel):
    latitude: float
    longitude: float


class PropertyImage(CamelCaseModel):
    url: str
    caption: Optional[str] = None
    src_url: str


class PropertyImages(CamelCaseModel):
    images: list[PropertyImage]
    main_image_src: str
    main_map_image_src: str


class ListingUpdate(CamelCaseModel):
    listing_update_reason: Optional[str] = None
    listing_update_date: Optional[pydantic.AwareDatetime] = None


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
    brand_plus_logo_uri: Optional[str] = pydantic.Field(None, alias="brandPlusLogoURI")
    contact_telephone: Optional[str] = None
    branch_display_name: Optional[str] = None
    branch_name: Optional[str] = None
    brand_trading_name: Optional[str] = None
    branch_landing_page_url: Optional[str] = None
    development: bool
    show_reduced_properties: Optional[bool] = None
    has_brand_plus: Optional[bool] = None
    commercial: bool
    show_on_map: Optional[bool] = None
    enhanced_listing: Optional[bool] = None
    development_content: Optional[DevelopmentContent] = None
    build_to_rent: Optional[bool] = None
    build_to_rent_benefits: list[BuildToRentBenefits]
    brand_plus_logo_url: Optional[str] = None
    media_server_url: Optional[str] = None
    update_date: Optional[pydantic.AwareDatetime] = None
    primary_brand_colour: Optional[str] = None


class ProductLabel(CamelCaseModel):
    product_label_text: Optional[str] = None
    spotlight_label: bool


class MatchingLozenges(CamelCaseModel):
    type: str | None = None
    priority: int | None = None


class LozengeModel(CamelCaseModel):
    matching_lozenges: list[MatchingLozenges]


class Tenure(CamelCaseModel):
    tenure_type: Optional[str] = None


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
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    number_of_images: int
    number_of_floorplans: int
    summary: str
    display_address: str
    images: list[PropertyImage]
    property_images: PropertyImages
    property_sub_type: Optional[str] = None
    listing_update: Optional[ListingUpdate] = None
    price: Price
    premium_listing: bool
    featured_property: bool
    customer: Customer
    auction: bool
    display_size: Optional[str] = None
    property_url: str
    channel: str
    saved: bool
    online_viewings_available: bool
    lozenge_model: LozengeModel


class MapProperty(_PropertyBase):
    """Properties returned by the map search endpoint."""


class ListingProperty(_PropertyBase):
    """Properties returned by the listing search endpoint."""

    number_of_virtual_tours: int
    country_code: str
    distance: Optional[float] = None
    transaction_type: str
    tenure: Optional[Tenure] = None
    let_available_date: Optional[pydantic.AwareDatetime] = None
    commercial_search_prominence_selected: bool = False
    product_label: Optional[ProductLabel] = None
    commercial: bool = False
    development: bool = False
    residential: bool = False
    students: bool = False
    fees_apply: Optional[bool] = None
    fees_apply_text: Optional[str] = None
    show_on_map: Optional[bool] = None
    contact_url: Optional[str] = None
    static_map_url: Optional[str] = None
    first_visible_date: Optional[pydantic.AwareDatetime] = None
    keywords: list[str] = []
    tags: list[str] = []
    keyword_match_type: Optional[str] = None
    hidden: bool = False
    street_view: Optional[StreetView] = None
    enquired_timestamp: Optional[pydantic.AwareDatetime] = None
    update_date: Optional[pydantic.AwareDatetime] = None
    enquiry_added_timestamp: Optional[pydantic.AwareDatetime] = None
    enquiry_called_timestamp: Optional[pydantic.AwareDatetime] = None
    reviews: Optional[Any] = None
    key_features: list[KeyFeature] = []
    enhanced_listing: Optional[bool] = None
    formatted_branch_name: Optional[str] = None
    added_or_reduced: Optional[str] = None
    formatted_distance: Optional[str] = None
    heading: Optional[str] = None
    property_type_full_description: Optional[str] = None
    display_status: Optional[str] = None
    is_recent: Optional[bool] = None
    has_brand_plus: Optional[bool] = None
    is_rdl_property: Optional[bool] = None
    additional_properties: Optional[list[Any]] = None
    number_of_additional_properties: Optional[int] = None
