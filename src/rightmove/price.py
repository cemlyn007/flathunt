from typing import Optional
from rightmove import models


def normalize(price: models.Price) -> Optional[float]:
    if price is None:
        return None
    # else...
    match price.frequency:
        case "monthly":
            amount = price.amount
        case "weekly":
            amount = price.amount * 52 / 12
        case "daily":
            amount = price.amount * 365 / 12
        case "yearly":
            amount = price.amount / 12
        case _:
            raise ValueError(f"Unknown frequency {price.frequency}")
    return amount
