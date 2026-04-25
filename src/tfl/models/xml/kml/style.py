from pydantic_xml import BaseXmlModel, attr, element

from tfl.models.xml.kml.icon_style import IconStyle


class Style(BaseXmlModel, tag="Style"):
    id: str = attr()
    icon_style: IconStyle = element(tag="IconStyle")
