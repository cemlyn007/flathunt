from pydantic_xml import BaseXmlModel, element


class Attribution(BaseXmlModel, tag="Attribution"):
    url: str = element(tag="Url")
    text: str = element(tag="Text")
    logo: str = element(tag="Logo")
