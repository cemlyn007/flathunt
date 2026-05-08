from pydantic_xml import BaseXmlModel, element

from tfl.models.xml.accessibility.booking_hall_to_platform import BookingHallToPlatform
from tfl.models.xml.accessibility.entrance_to_booking_hall import EntranceToBookingHall
from tfl.models.xml.accessibility.platform_to_train import PlatformToTrain


class Entrance(BaseXmlModel, tag="entrance"):
    name: str = element(tag="name")
    entrance_to_booking_hall: EntranceToBookingHall | None = element(
        tag="entranceToBookingHall", default=None
    )
    entrance_to_booking_hall_direction: str | None = element(
        tag="entranceToBookingHallDirection", default=None
    )
    entrance_to_booking_hall_steps: str | None = element(
        tag="entranceToBookingHallSteps", default=None
    )
    booking_hall_to_platform: list[BookingHallToPlatform] = element(
        tag="bookingHallToPlatform", default=[]
    )
    platform_to_train: list[PlatformToTrain] = element(
        tag="platformToTrain", default=[]
    )
