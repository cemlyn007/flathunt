import json
import re

from rightmove.models.property_details import PropertyDetails

_PAGE_MODEL_RE = re.compile(r"window\.PAGE_MODEL\s*=\s*(\{)", re.DOTALL)


def parse_property_details(html: str) -> PropertyDetails:
    """Extract and validate property details from a Rightmove property page.

    Args:
        html: Full HTML source of a Rightmove property page.

    Returns:
        A ``PropertyDetails`` instance parsed from ``window.PAGE_MODEL``.

    Raises:
        ValueError: If ``window.PAGE_MODEL`` is not found in the HTML.
    """
    match = _PAGE_MODEL_RE.search(html)
    if not match:
        raise ValueError("window.PAGE_MODEL not found in page HTML.")
    obj, _ = json.JSONDecoder().raw_decode(html, match.start(1))
    return PropertyDetails.model_validate(obj["propertyData"])
