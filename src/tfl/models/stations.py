from pydantic_xml import BaseXmlModel, element

from tfl.models.station import Station


class Stations(BaseXmlModel, tag="stations"):
    station: list[Station] = element(tag="station", default=[])
