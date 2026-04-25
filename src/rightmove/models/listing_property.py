from typing import Any

import pydantic

from rightmove.models._property_base import _PropertyBase
from rightmove.models.key_feature import KeyFeature
from rightmove.models.product_label import ProductLabel
from rightmove.models.street_view import StreetView
from rightmove.models.tenure import Tenure


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
