from pydantic_xml import BaseXmlModel, element

from tfl.models.xml.accessibility.opening_hour import OpeningHour


class OpeningHours(BaseXmlModel, tag="openingHours"):
    opening_hour: list[OpeningHour] = element(tag="openingHour", default=[])
