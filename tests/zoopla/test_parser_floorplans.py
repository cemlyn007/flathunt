"""Tests for floor plan URL extraction from Zoopla listing pages."""

import json
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from zoopla.parser import _parse_floorplan_urls, parse_zoopla_listing_html

_FIXTURES = Path(__file__).parent / "fixtures"
_LISTING_URL = "https://www.zoopla.co.uk/for-sale/details/73095703/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wrap_rsc(payload: Any) -> str:
    """Build a minimal HTML page containing one __next_f.push chunk.

    ``payload`` is any JSON-serialisable value.  It is serialised to a JSON
    string, then embedded inside the ``self.__next_f.push([1,"..."])`` wrapper
    exactly as Zoopla's server-side renderer emits it.
    """
    inner = json.dumps(payload)  # e.g. '{"floorPlan": [...]}'
    chunk = json.dumps("0:" + inner)  # JSON-escaped string literal for JS
    return f"<html><body><script>self.__next_f.push([1,{chunk}])</script></body></html>"


# ---------------------------------------------------------------------------
# Group 1 — Real fixture
# ---------------------------------------------------------------------------


def test_real_fixture_returns_expected_floorplan_url() -> None:
    # Given  the saved HTML for listing 73095703
    # When   parse_zoopla_listing_html is called
    # Then   floorplan_urls contains exactly one known URL (and RSC pointer
    #        strings in the same buffer are silently ignored)
    html = (_FIXTURES / "listing_73095703.html").read_text(encoding="utf-8")
    detail = parse_zoopla_listing_html(html, _LISTING_URL)
    assert detail.floorplan_urls == [
        "https://lc.zoocdn.com/72b72db0777f9d04455ebd7dd81bd63471d4c74c.png"
    ]


# ---------------------------------------------------------------------------
# Group 2 — Synthetic shape-1: list of {"original": "<url>"}
# ---------------------------------------------------------------------------


def test_shape1_original_url_extracted() -> None:
    # Given  minimal HTML with floorPlan as a list of {"original": "<url>"} dicts
    # When   _parse_floorplan_urls is called
    # Then   the single URL is returned as-is
    html = _wrap_rsc({"floorPlan": [{"original": "https://lc.zoocdn.com/abc.png"}]})
    soup = BeautifulSoup(html, "html.parser")
    assert _parse_floorplan_urls(soup) == ["https://lc.zoocdn.com/abc.png"]


# ---------------------------------------------------------------------------
# Group 3 — Synthetic shape-2: {"image": [{"filename": "..."}]}
# ---------------------------------------------------------------------------


def test_shape2_filename_reconstructed_to_url() -> None:
    # Given  minimal HTML with floorPlan as a dict with an image list of filename dicts
    # When   _parse_floorplan_urls is called
    # Then   the URL is reconstructed by prepending the lc.zoocdn.com host
    html = _wrap_rsc({
        "floorPlan": {
            "image": [{"caption": None, "filename": "abc.png"}],
            "links": None,
            "pdf": None,
        }
    })
    soup = BeautifulSoup(html, "html.parser")
    assert _parse_floorplan_urls(soup) == ["https://lc.zoocdn.com/abc.png"]


# ---------------------------------------------------------------------------
# Group 4 — No floorPlan key
# ---------------------------------------------------------------------------


def test_no_floorplan_key_returns_empty_list() -> None:
    # Given  minimal HTML with valid JSON but no "floorPlan" key anywhere
    # When   _parse_floorplan_urls is called
    # Then   an empty list is returned
    html = _wrap_rsc({"someOtherKey": [{"original": "https://lc.zoocdn.com/abc.png"}]})
    soup = BeautifulSoup(html, "html.parser")
    assert _parse_floorplan_urls(soup) == []


# ---------------------------------------------------------------------------
# Group 5 — RSC reference pointer string is ignored
# ---------------------------------------------------------------------------


def test_rsc_pointer_string_is_ignored() -> None:
    # Given  minimal HTML where floorPlan is bound to an RSC reference string
    # When   _parse_floorplan_urls is called
    # Then   the string value is ignored (type-checked) and an empty list is returned
    html = _wrap_rsc({"floorPlan": "$5a:props:children:floor_plan"})
    soup = BeautifulSoup(html, "html.parser")
    assert _parse_floorplan_urls(soup) == []


# ---------------------------------------------------------------------------
# Group 6 — Multiple URLs, deduplication and ordering preserved
# ---------------------------------------------------------------------------


def test_multiple_urls_deduplicated_and_ordered() -> None:
    # Given  a shape-1 payload with three entries, the first two distinct and the
    #        third a duplicate of the first
    # When   _parse_floorplan_urls is called
    # Then   the result contains the two distinct URLs in first-seen order
    html = _wrap_rsc({
        "floorPlan": [
            {"original": "https://lc.zoocdn.com/first.png"},
            {"original": "https://lc.zoocdn.com/second.png"},
            {"original": "https://lc.zoocdn.com/first.png"},  # duplicate
        ]
    })
    soup = BeautifulSoup(html, "html.parser")
    assert _parse_floorplan_urls(soup) == [
        "https://lc.zoocdn.com/first.png",
        "https://lc.zoocdn.com/second.png",
    ]


# ---------------------------------------------------------------------------
# Group 7 — End-to-end: floorplan_urls wired through parse_zoopla_listing_html
# ---------------------------------------------------------------------------


def test_floorplan_urls_wired_through_parse_zoopla_listing_html() -> None:
    # Given  minimal HTML containing a single shape-1 floorPlan payload
    # When   parse_zoopla_listing_html is called
    # Then   the returned ZooplaListingDetail has the expected floorplan_urls
    html = _wrap_rsc({"floorPlan": [{"original": "https://lc.zoocdn.com/wire.png"}]})
    detail = parse_zoopla_listing_html(
        html, "https://www.zoopla.co.uk/for-sale/details/99999999/"
    )
    assert detail.floorplan_urls == ["https://lc.zoocdn.com/wire.png"]
