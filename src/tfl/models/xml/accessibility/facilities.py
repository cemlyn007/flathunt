from pydantic_xml import BaseXmlModel, element

from tfl.models.xml.accessibility.facility import Facility


class Facilities(BaseXmlModel, tag="facilities"):
    facility: list[Facility] = element(tag="facility", default=[])
