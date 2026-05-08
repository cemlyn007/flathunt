import json
import re
from typing import Any

from rightmove.models.property_details import PropertyDetails

_PAGE_MODEL_NEW_RE = re.compile(r"window\.__PAGE_MODEL\s*=\s*(\{)", re.DOTALL)
_PAGE_MODEL_OLD_RE = re.compile(r"window\.PAGE_MODEL\s*=\s*(\{)", re.DOTALL)


def _resolve(idx: int, arr: list[Any], cache: dict[int, Any]) -> Any:
    if idx in cache:
        return cache[idx]
    val = arr[idx]
    if isinstance(val, dict):
        out: dict[str, Any] = {}
        cache[idx] = out
        for k, v in val.items():
            out[k] = _resolve(v, arr, cache)
        return out
    if isinstance(val, list):
        out_l: list[Any] = []
        cache[idx] = out_l
        out_l.extend(_resolve(v, arr, cache) for v in val)
        return out_l
    cache[idx] = val
    return val


def _extract_property_data(html: str) -> dict[str, Any]:
    new_match = _PAGE_MODEL_NEW_RE.search(html)
    if new_match:
        outer, _ = json.JSONDecoder().raw_decode(html, new_match.start(1))
        arr = json.loads(outer["data"])
        root = _resolve(0, arr, {})
        return root["propertyData"]

    old_match = _PAGE_MODEL_OLD_RE.search(html)
    if old_match:
        obj, _ = json.JSONDecoder().raw_decode(html, old_match.start(1))
        return obj["propertyData"]

    raise ValueError(
        "Neither window.__PAGE_MODEL nor window.PAGE_MODEL found in page HTML."
    )


def parse_property_details(html: str) -> PropertyDetails:
    """Extract and validate property details from a Rightmove property page.

    Supports both the legacy ``window.PAGE_MODEL = {...}`` global and the
    current ``window.__PAGE_MODEL = {data: <flatted JSON>, encoding: ...}``
    format, where ``data`` is a flat array of values referenced by integer
    index from the root at ``arr[0]``.

    Args:
        html: Full HTML source of a Rightmove property page.

    Returns:
        A ``PropertyDetails`` instance parsed from the inline page model.

    Raises:
        ValueError: If neither global is present in the HTML.
    """
    return PropertyDetails.model_validate(_extract_property_data(html))
