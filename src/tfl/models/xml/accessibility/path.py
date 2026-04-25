from pydantic_xml import BaseXmlModel, element


class Path(BaseXmlModel, tag="path"):
    heading: str = element(tag="heading")
    path_description: str = element(tag="pathDescription")
