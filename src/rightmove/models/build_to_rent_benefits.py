from rightmove.models.base import CamelCaseModel


class BuildToRentBenefits(CamelCaseModel):
    id: int
    label: str
    icon: str
    position_on_page: int
