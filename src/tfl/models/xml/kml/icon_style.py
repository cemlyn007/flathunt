from pydantic_xml import BaseXmlModel, element

from tfl.models.xml.kml.icon import Icon


class IconStyle(BaseXmlModel, tag="IconStyle"):
    icon: Icon = element(tag="Icon")
