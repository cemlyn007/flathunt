import pydantic

from rightmove.models.base import CamelCaseModel
from rightmove.models.build_to_rent_benefits import BuildToRentBenefits
from rightmove.models.development_content import DevelopmentContent


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
