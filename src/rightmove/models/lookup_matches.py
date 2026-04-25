from rightmove.models.base import CamelCaseModel
from rightmove.models.lookup_match import LookupMatch


class LookupMatches(CamelCaseModel):
    matches: list[LookupMatch]
