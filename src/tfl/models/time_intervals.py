from pydantic_xml import BaseXmlModel, attr, element

from tfl.models.time_interval import TimeInterval


class TimeIntervals(BaseXmlModel, tag="timeIntervals"):
    type: str = attr()
    time_interval: list[TimeInterval] = element(tag="timeInterval", default=[])
