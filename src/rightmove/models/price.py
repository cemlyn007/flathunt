from rightmove.models.base import CamelCaseModel
from rightmove.models.display_price import DisplayPrice


class Price(CamelCaseModel):
    amount: int
    frequency: str
    currency_code: str | None = None
    display_prices: list[DisplayPrice] | None = None
