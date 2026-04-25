from rightmove.models.base import CamelCaseModel
from rightmove.models.highlight import Highlight


class LookupMatch(CamelCaseModel):
    id: str
    type: str
    display_name: str
    highlighting: str
    highlights: list[Highlight]

    @property
    def location_identifier(self) -> str:
        return f"{self.type}^{self.id}"
