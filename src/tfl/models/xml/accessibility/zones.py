from pydantic_xml import BaseXmlModel, element


class Zones(BaseXmlModel, tag="zones"):
    zone: list[str] = element(tag="zone", default=[])
