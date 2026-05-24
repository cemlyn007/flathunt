"""Tests for listing photo-gallery extraction from Zoopla listing pages."""

import json
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from zoopla.parser import _parse_image_urls, parse_zoopla_listing_html

_FIXTURES = Path(__file__).parent / "fixtures"
_LISTING_URL = "https://www.zoopla.co.uk/for-sale/details/73095703/"

# The gallery for listing 73095703, in the order Zoopla emits it inside the RSC
# ``propertyImage`` array.
_EXPECTED_FILENAMES = [
    "8dab3330f792fb8b59f7fce20d4e1a011a2cfcf9.jpg",
    "394d9cdba9b0eb99b656d94ae63217ccb01b4681.jpg",
    "97d55fa68d7e5b0260e0ee84ff4479a1215cdd06.jpg",
    "edd5dd9b9c58fbbce33b8e200b6a0da30a8e0bbf.jpg",
    "0eb2af4c7f0054a53e32e79202ee98c6f9c27a49.jpg",
    "2236352ac5fd3b981ee053f749519753bd2ded76.jpg",
    "6bef3254ccea7d265fde78325f247f9744866682.jpg",
    "f3b64d5d609dce0083a0c28f9c251e2a9c230d8b.jpg",
    "775ef3d324bf4ebdec1ad68812ecbec6b7f31f66.jpg",
    "fd41ae13bc5ee69e6bc6c807e0b5d04852773c76.jpg",
    "6e99d5cf182f59b0719779c481b9d395d0059151.jpg",
]


def _wrap_rsc(payload: Any) -> str:
    inner = json.dumps(payload)
    chunk = json.dumps("0:" + inner)
    return f"<html><body><script>self.__next_f.push([1,{chunk}])</script></body></html>"


# ---------------------------------------------------------------------------
# Group 1 — Real fixture
# ---------------------------------------------------------------------------


def test_real_fixture_returns_full_photo_gallery() -> None:
    # Given  the saved HTML for listing 73095703, whose 11-photo gallery lives in
    #        the RSC ``propertyImage`` array (only the hero image is in JSON-LD)
    # When   parse_zoopla_listing_html is called
    # Then   every gallery image is returned as a full-size zoocdn URL, in order —
    #        not just the single JSON-LD hero image
    html = (_FIXTURES / "listing_73095703.html").read_text(encoding="utf-8")
    detail = parse_zoopla_listing_html(html, _LISTING_URL)
    assert detail.image_urls == [
        f"https://lid.zoocdn.com/u/1024/768/{fn}" for fn in _EXPECTED_FILENAMES
    ]


# ---------------------------------------------------------------------------
# Group 2 — propertyImage filename array is expanded to full URLs
# ---------------------------------------------------------------------------


def test_property_image_filename_list_expands_to_full_urls() -> None:
    # Given  an RSC object holding the listing's propertyImage array of {filename}
    #        dicts (filenames only, no host — the shape Zoopla emits)
    # When   _parse_image_urls is called
    # Then   each filename becomes a full-size zoocdn image URL, in order
    html = _wrap_rsc({
        "listingId": "73095703",
        "propertyImage": [
            {"caption": None, "filename": "a1.jpg"},
            {"caption": None, "filename": "b2.jpg"},
            {"caption": None, "filename": "c3.jpg"},
        ],
    })
    soup = BeautifulSoup(html, "html.parser")
    assert _parse_image_urls(soup, {}, "73095703") == [
        "https://lid.zoocdn.com/u/1024/768/a1.jpg",
        "https://lid.zoocdn.com/u/1024/768/b2.jpg",
        "https://lid.zoocdn.com/u/1024/768/c3.jpg",
    ]


# ---------------------------------------------------------------------------
# Group 3 — gallery is keyed to the listing, not "similar properties"
# ---------------------------------------------------------------------------


def test_gallery_keyed_to_matching_listing_id_ignores_similar_listings() -> None:
    # Given  the RSC payload contains a similar-listing gallery (different listingId)
    #        as well as this listing's own gallery
    # When   _parse_image_urls is called with the listing's id
    # Then   only the matching listing's gallery is returned
    html = _wrap_rsc([
        {
            "listingId": "999999",
            "propertyImage": [
                {"filename": "similar1.jpg"},
                {"filename": "similar2.jpg"},
            ],
        },
        {
            "listingId": "73095703",
            "propertyImage": [
                {"filename": "mine1.jpg"},
                {"filename": "mine2.jpg"},
                {"filename": "mine3.jpg"},
            ],
        },
    ])
    soup = BeautifulSoup(html, "html.parser")
    assert _parse_image_urls(soup, {}, "73095703") == [
        "https://lid.zoocdn.com/u/1024/768/mine1.jpg",
        "https://lid.zoocdn.com/u/1024/768/mine2.jpg",
        "https://lid.zoocdn.com/u/1024/768/mine3.jpg",
    ]


# ---------------------------------------------------------------------------
# Group 4 — fallback to JSON-LD image when no gallery is present
# ---------------------------------------------------------------------------


def test_falls_back_to_json_ld_image_when_no_gallery() -> None:
    # Given  a page with no propertyImage gallery in the RSC payload
    # When   _parse_image_urls is called with a JSON-LD image present
    # Then   the single JSON-LD image is returned as a fallback
    html = _wrap_rsc({"unrelated": "data"})
    soup = BeautifulSoup(html, "html.parser")
    ld = {"image": "https://lid.zoocdn.com/u/1024/768/zzz.jpg"}
    assert _parse_image_urls(soup, ld, "73095703") == [
        "https://lid.zoocdn.com/u/1024/768/zzz.jpg"
    ]
