from rightmove.models.base import CamelCaseModel


class Highlight(CamelCaseModel):
    text: str
    highlighted: bool


class LookupMatch(CamelCaseModel):
    id: str
    type: str
    display_name: str
    highlighting: str
    highlights: list[Highlight]

    @property
    def location_identifier(self) -> str:
        return f"{self.type}^{self.id}"


class LookupMatches(CamelCaseModel):
    matches: list[LookupMatch]
