from rightmove.models.base import CamelCaseModel


class DisplayPrice(CamelCaseModel):
    display_price: str
    display_price_qualifier: str
