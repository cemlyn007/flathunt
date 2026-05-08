from pydantic_xml import BaseXmlModel, element

from tfl.models.xml.kml.point import Point


class Placemark(BaseXmlModel, tag="Placemark"):
    name: str = element(tag="name")
    description: str = element(tag="description")
    point: Point = element(tag="Point")
    style_url: str = element(tag="styleUrl")
