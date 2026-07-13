import pydantic

from rightmove.models.property_details import PropertyDetails


class PropertyDetailsFetchResult(pydantic.BaseModel):
    """Outcome of fetching a Rightmove listing's detail page.

    ``is_delisted`` is True only when Rightmove confirmed via HTTP 404/410 that
    the listing no longer exists. Any other fetch failure (timeout, blocked,
    parse error, ...) leaves both fields at their defaults — that state is
    unknown, not confirmed-gone, and must be treated accordingly downstream.
    """

    details: PropertyDetails | None = None
    is_delisted: bool = False
