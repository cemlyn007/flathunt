from pydantic_xml import BaseXmlModel, element

from tfl.models.xml.accessibility.time_intervals import TimeIntervals


class OpeningHour(BaseXmlModel, tag="openingHour"):
    entrance: str = element(tag="entrance")
    time_intervals: list[TimeIntervals] = element(tag="timeIntervals", default=[])
