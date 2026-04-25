import pydantic

from tfl.models.base import TflModel


class ValidityPeriod(TflModel):
    type: str = pydantic.Field(alias="$type")
    from_date: str | None = None
    to_date: str | None = None
    is_now: bool | None = None
