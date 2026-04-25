from rightmove.models.base import CamelCaseModel


class ProductLabel(CamelCaseModel):
    product_label_text: str | None = None
    spotlight_label: bool
