from rightmove.models.base import CamelCaseModel


class Highlight(CamelCaseModel):
    text: str
    highlighted: bool
