from pydantic_xml import BaseXmlModel, element

from tfl.models.xml.kml.attribution import Attribution
from tfl.models.xml.kml.header import Header
from tfl.models.xml.kml.stations import Stations
from tfl.models.xml.kml.style import Style


class Root(BaseXmlModel, tag="Root"):
    name: str = element(tag="name")
    open: int = element(tag="open")
    description: str = element(tag="description")
    header: Header = element(tag="Header")
    attribution: Attribution | None = element(tag="Attribution", default=None)
    styles: list[Style] = element(tag="Style", default=[])
    stations: Stations = element(tag="stations")
