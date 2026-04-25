from pydantic_xml import BaseXmlModel, element


class EntranceToBookingHall(BaseXmlModel, tag="entranceToBookingHall"):
    entrance_to_booking_hall_direction: str | None = element(
        tag="entranceToBookingHallDirection", default=None
    )
    entrance_to_booking_hall_steps: str | None = element(
        tag="entranceToBookingHallSteps", default=None
    )
