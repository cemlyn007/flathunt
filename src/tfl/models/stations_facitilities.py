from typing import Optional

from pydantic import computed_field
from pydantic_xml import BaseXmlModel, attr, element


class Header(BaseXmlModel, tag="Header"):
    identifier: str = element(tag="Identifier")
    display_title: str = element(tag="DisplayTitle")
    version: str = element(tag="Version")
    publish_date_time: str = element(tag="PublishDateTime")
    canonical: Optional[str] = attr(name="canonical", default=None)
    author: str = element(tag="Author")
    owner: str = element(tag="Owner")
    refresh_rate: int = element(tag="RefreshRate")
    max_latency: int = element(tag="Max_Latency")
    time_to_error: int = element(tag="TimeToError")
    schedule: str = element(tag="Schedule")


class Attribution(BaseXmlModel, tag="Attribution"):
    url: str = element(tag="Url")
    text: str = element(tag="Text")
    logo: str = element(tag="Logo")


class ContactDetails(BaseXmlModel, tag="contactDetails"):
    address: str = element(tag="address")
    phone: str = element(tag="phone")


class ServingLines(BaseXmlModel, tag="servingLines"):
    serving_line: list[str] = element(tag="servingLine", default=[])


class Zones(BaseXmlModel, tag="zones"):
    zone: list[str] = element(tag="zone", default=[])


class Facility(BaseXmlModel, tag="facility"):
    name: str = attr()
    value: str


class Facilities(BaseXmlModel, tag="facilities"):
    facility: list[Facility] = element(tag="facility", default=[])


class Point(BaseXmlModel, tag="Point"):
    coordinates: str = element(tag="coordinates")

    @computed_field
    @property
    def longitude(self) -> float:
        """Extract longitude from KML coordinates (longitude,latitude,altitude)."""
        return float(self.coordinates.split(",")[0])

    @computed_field
    @property
    def latitude(self) -> float:
        """Extract latitude from KML coordinates (longitude,latitude,altitude)."""
        return float(self.coordinates.split(",")[1])

    @computed_field
    @property
    def altitude(self) -> float:
        """Extract altitude from KML coordinates (longitude,latitude,altitude)."""
        coords = self.coordinates.split(",")
        return float(coords[2]) if len(coords) > 2 else 0.0


class Placemark(BaseXmlModel, tag="Placemark"):
    name: str = element(tag="name")
    description: str = element(tag="description")
    point: Point = element(tag="Point")
    style_url: str = element(tag="styleUrl")


class PlatformToTrain(BaseXmlModel, tag="platformToTrain"):
    train_name: str | None = element(tag="trainName", default=None)
    platform_to_train_steps: str | None = element(
        tag="platformToTrainSteps", default=None
    )


class Path(BaseXmlModel, tag="path"):
    heading: str = element(tag="heading")
    path_description: str = element(tag="pathDescription")


class BookingHallToPlatform(BaseXmlModel, tag="bookingHallToPlatform"):
    point_name: str | None = element(tag="pointName", default=None)
    path_description: str | None = element(tag="pathDescription", default=None)
    path: list[Path] = element(tag="path", default=[])


class EntranceToBookingHall(BaseXmlModel, tag="entranceToBookingHall"):
    entrance_to_booking_hall_direction: str | None = element(
        tag="entranceToBookingHallDirection", default=None
    )
    entrance_to_booking_hall_steps: str | None = element(
        tag="entranceToBookingHallSteps", default=None
    )


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


class Entrances(BaseXmlModel, tag="entrances"):
    entrance: list[Entrance] = element(tag="entrance", default=[])


class TimeInterval(BaseXmlModel, tag="timeInterval"):
    from_time: str = element(tag="from")
    to_time: str = element(tag="to")


class TimeIntervals(BaseXmlModel, tag="timeIntervals"):
    type: str = attr()
    time_interval: list[TimeInterval] = element(tag="timeInterval", default=[])


class OpeningHour(BaseXmlModel, tag="openingHour"):
    entrance: str = element(tag="entrance")
    time_intervals: list[TimeIntervals] = element(tag="timeIntervals", default=[])


class OpeningHours(BaseXmlModel, tag="openingHours"):
    opening_hour: list[OpeningHour] = element(tag="openingHour", default=[])


class Station(BaseXmlModel, tag="station"):
    id: str = attr()
    type: str = attr()
    name: str = element(tag="name")
    contact_details: ContactDetails = element(tag="contactDetails")
    serving_lines: Optional[ServingLines] = element(tag="servingLines", default=None)
    zones: Optional[Zones] = element(tag="zones", default=None)
    facilities: Optional[Facilities] = element(tag="facilities", default=None)
    entrances: Optional[Entrances] = element(tag="entrances", default=None)
    opening_hours: Optional[OpeningHours] = element(tag="openingHours", default=None)
    placemark: Optional[Placemark] = element(tag="Placemark", default=None)


class Stations(BaseXmlModel, tag="stations"):
    station: list[Station] = element(tag="station", default=[])


class Icon(BaseXmlModel, tag="Icon"):
    href: str = element(tag="href")


class IconStyle(BaseXmlModel, tag="IconStyle"):
    icon: Icon = element(tag="Icon")


class Style(BaseXmlModel, tag="Style"):
    id: str = attr()
    icon_style: IconStyle = element(tag="IconStyle")


class Root(BaseXmlModel, tag="Root"):
    name: str = element(tag="name")
    open: int = element(tag="open")
    description: str = element(tag="description")
    header: Header = element(tag="Header")
    attribution: Optional[Attribution] = element(tag="Attribution", default=None)
    styles: list[Style] = element(tag="Style", default=[])
    stations: Stations = element(tag="stations")
