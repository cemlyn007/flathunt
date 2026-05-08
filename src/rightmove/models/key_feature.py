from rightmove.models.base import CamelCaseModel


class KeyFeature(CamelCaseModel):
    order: int
    description: str
    html_description: str
