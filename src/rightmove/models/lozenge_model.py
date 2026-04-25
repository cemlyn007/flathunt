from rightmove.models.base import CamelCaseModel
from rightmove.models.matching_lozenges import MatchingLozenges


class LozengeModel(CamelCaseModel):
    matching_lozenges: list[MatchingLozenges]
