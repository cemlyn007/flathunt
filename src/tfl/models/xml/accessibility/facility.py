from pydantic_xml import BaseXmlModel, attr


class Facility(BaseXmlModel, tag="facility"):
    name: str = attr()
    value: str
