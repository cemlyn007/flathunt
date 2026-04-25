from rightmove.models.base import CamelCaseModel


class Tenure(CamelCaseModel):
    tenure_type: str | None = None
