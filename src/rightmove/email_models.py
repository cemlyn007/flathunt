from datetime import datetime

from pydantic import BaseModel

__all__ = ["RightmoveProperty", "RightmovePropertyAlert"]


class RightmoveProperty(BaseModel):
    listing_id: str
    url: str
    image_url: str | None
    price_gbp: int | None
    price_text: str
    price_qualifier: str | None
    is_reduced: bool
    property_type: str | None
    address: str | None
    marketed_by: str | None
    agent_phone: str | None
    photo_count: int | None
    floorplan_count: int | None


class RightmovePropertyAlert(BaseModel):
    message_id: str
    subject: str
    received_at: datetime
    properties: list[RightmoveProperty]
