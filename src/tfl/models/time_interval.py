from pydantic_xml import BaseXmlModel, element


class TimeInterval(BaseXmlModel, tag="timeInterval"):
    from_time: str = element(tag="from")
    to_time: str = element(tag="to")
