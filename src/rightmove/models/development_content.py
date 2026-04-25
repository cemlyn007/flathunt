from typing import Any

from rightmove.models.base import CamelCaseModel


class DevelopmentContent(CamelCaseModel):
    headline: Any | None = None
    "Currently the type is not known."
    features: Any | None = None
    "Currently the type is not known."
