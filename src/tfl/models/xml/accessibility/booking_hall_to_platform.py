from pydantic_xml import BaseXmlModel, element

from tfl.models.xml.accessibility.path import Path


class BookingHallToPlatform(BaseXmlModel, tag="bookingHallToPlatform"):
    point_name: str | None = element(tag="pointName", default=None)
    path_description: str | None = element(tag="pathDescription", default=None)
    path: list[Path] = element(tag="path", default=[])
