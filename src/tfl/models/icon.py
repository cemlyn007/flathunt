from pydantic_xml import BaseXmlModel, element


class Icon(BaseXmlModel, tag="Icon"):
    href: str = element(tag="href")
