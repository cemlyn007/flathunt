from rightmove.models.base import CamelCaseModel


class PropertyImage(CamelCaseModel):
    url: str
    caption: str | None = None
    src_url: str
