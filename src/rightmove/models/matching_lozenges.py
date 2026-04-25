from rightmove.models.base import CamelCaseModel


class MatchingLozenges(CamelCaseModel):
    type: str | None = None
    priority: int | None = None
