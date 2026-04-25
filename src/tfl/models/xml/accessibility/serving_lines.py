from pydantic_xml import BaseXmlModel, element


class ServingLines(BaseXmlModel, tag="servingLines"):
    serving_line: list[str] = element(tag="servingLine", default=[])
