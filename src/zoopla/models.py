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
