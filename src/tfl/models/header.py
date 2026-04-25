from pydantic_xml import BaseXmlModel, attr, element


class Header(BaseXmlModel, tag="Header"):
    identifier: str = element(tag="Identifier")
    display_title: str = element(tag="DisplayTitle")
    version: str = element(tag="Version")
    publish_date_time: str = element(tag="PublishDateTime")
    canonical: str | None = attr(name="canonical", default=None)
    author: str = element(tag="Author")
    owner: str = element(tag="Owner")
    refresh_rate: int = element(tag="RefreshRate")
    max_latency: int = element(tag="Max_Latency")
    time_to_error: int = element(tag="TimeToError")
    schedule: str = element(tag="Schedule")
