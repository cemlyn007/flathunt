from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class AlertType(StrEnum):
    PRICE_REDUCED = "price_reduced"
    NEW_LISTING = "new_listing"


class ZooplaProperty(BaseModel):
    listing_id: str
    url: str
    image_url: str | None
    price_gbp: int | None
    price_text: str
    reduction_gbp: int | None
    reduction_text: str | None
    property_type: str | None
    address: str | None
    agent_logo_url: str | None
    agent_phone: str | None


class ZooplaPropertyAlert(BaseModel):
    message_id: str
    subject: str
    received_at: datetime
    alert_type: AlertType
    properties: list[ZooplaProperty]


class ZooplaListingDetail(BaseModel):
    listing_id: str
    url: str
    price_gbp: int | None
    price_qualifier: str | None
    address: str | None
    property_type: str | None
    bedrooms: int | None
    bathrooms: int | None
    receptions: int | None
    floor_area_sqft: int | None
    tenure: str | None
    service_charge: str | None
    council_tax_band: str | None
    ground_rent: str | None
    ground_rent_review_date: str | None
    chain_free: bool | None
    listing_condition: str | None
    description: str | None
    key_features: list[str]
    agent_name: str | None
    agent_logo_url: str | None
    image_urls: list[str]
    floorplan_urls: list[str] = []
    date_posted: datetime | None
    latitude: float | None
    longitude: float | None
