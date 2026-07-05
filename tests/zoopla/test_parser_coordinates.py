"""Tests for listing coordinate extraction from Zoopla listing pages.

The listing's location block pairs its coordinates with an ``outcode`` (postcode
district).  Resale (``/for-sale/``) pages additionally tag the block with a
``uprn`` and ``postalCode``; new-build (``/new-homes/``) units have no UPRN yet.
The parser therefore anchors on ``outcode`` so both listing types resolve, while
still ignoring the nearby-POI coordinates (stations, schools, EV-charging
points, locality markers) that share the page but carry no ``outcode``.
"""

import json
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from zoopla.parser import _parse_coordinates, parse_zoopla_listing_html

_FIXTURES = Path(__file__).parent / "fixtures"
_LISTING_URL = "https://www.zoopla.co.uk/for-sale/details/73095703/"


def _wrap_rsc(payload: Any) -> str:
    inner = json.dumps(payload)
    chunk = json.dumps("0:" + inner)
    return f"<html><body><script>self.__next_f.push([1,{chunk}])</script></body></html>"


# ---------------------------------------------------------------------------
# Group 1 — Real fixture
# ---------------------------------------------------------------------------


def test_real_fixture_returns_listing_coordinates() -> None:
    # Given  the saved HTML for listing 73095703
    # When   parse_zoopla_listing_html is called
    # Then   latitude and longitude match the listing's coordinates (not those
    #        of any nearby EV charging station that also appears in the RSC payload)
    html = (_FIXTURES / "listing_73095703.html").read_text(encoding="utf-8")
    detail = parse_zoopla_listing_html(html, _LISTING_URL)
    assert detail.latitude == 51.525703
    assert detail.longitude == -0.099569


# ---------------------------------------------------------------------------
# Group 2 — Nested shape: resale location (coordinates child + uprn + outcode)
# ---------------------------------------------------------------------------


def test_nested_coordinates_under_resale_location_are_extracted() -> None:
    # Given  a resale location object with nested coordinates plus outcode, uprn
    #        and postalCode siblings (current /for-sale/ shape)
    # When   _parse_coordinates is called
    # Then   latitude and longitude are pulled from the nested coordinates dict
    html = _wrap_rsc({
        "location": {
            "outcode": "EC1V",
            "postalCode": "EC1V 7DX",
            "coordinates": {"latitude": 51.5, "longitude": -0.1},
            "uprn": "5300101867",
        }
    })
    soup = BeautifulSoup(html, "html.parser")
    assert _parse_coordinates(soup) == (51.5, -0.1)


# ---------------------------------------------------------------------------
# Group 3 — New-build shape: coordinates + outcode, no uprn (regression guard)
# ---------------------------------------------------------------------------


def test_new_build_coordinates_without_uprn_are_extracted() -> None:
    # Given  a new-build location object with coordinates and outcode but NO uprn
    #        (the /new-homes/ shape — units have no UPRN yet)
    # When   _parse_coordinates is called
    # Then   the coordinates are still extracted.  Regression guard: the previous
    #        uprn-only anchor silently returned (None, None) for every new-build
    #        listing, which surfaced as a missing commute duration in the email.
    html = _wrap_rsc({
        "location": {
            "outcode": "E16",
            "coordinates": {"latitude": 51.511145, "longitude": 0.017929},
        }
    })
    soup = BeautifulSoup(html, "html.parser")
    assert _parse_coordinates(soup) == (51.511145, 0.017929)


# ---------------------------------------------------------------------------
# Group 4 — Flat shape: latitude/longitude as siblings of outcode
# ---------------------------------------------------------------------------


def test_flat_coordinates_alongside_outcode_are_extracted() -> None:
    # Given  an object with flat latitude/longitude alongside an outcode (alternate
    #        shape Zoopla emits inside the address payload)
    # When   _parse_coordinates is called
    # Then   the flat fields are returned
    html = _wrap_rsc({
        "address": {
            "fullAddress": "1 Test Street, London",
            "latitude": 52.0,
            "longitude": -0.2,
            "outcode": "EC1V",
            "postcode": "EC1V 7DX",
        }
    })
    soup = BeautifulSoup(html, "html.parser")
    assert _parse_coordinates(soup) == (52.0, -0.2)


# ---------------------------------------------------------------------------
# Group 5 — Nearby POIs without an outcode are filtered out
# ---------------------------------------------------------------------------


def test_poi_coordinates_without_outcode_are_ignored() -> None:
    # Given  payload contains nearby-POI coordinate objects without an outcode (an
    #        EV station and a {address, coordinates, name} locality marker) plus a
    #        separate listing object carrying both outcode and coordinates
    # When   _parse_coordinates is called
    # Then   the listing coordinates are returned, not a POI's
    html = _wrap_rsc([
        {
            "name": "EV Station",
            "postcode": "EC1V 3QU",
            "coordinates": {"latitude": 51.526651, "longitude": -0.099756},
        },
        {
            "address": "Nearby Development",
            "name": "Some Wharf",
            "coordinates": {"latitude": 51.4, "longitude": -0.05},
        },
        {
            "location": {
                "outcode": "EC1V",
                "coordinates": {"latitude": 51.5, "longitude": -0.1},
            }
        },
    ])
    soup = BeautifulSoup(html, "html.parser")
    assert _parse_coordinates(soup) == (51.5, -0.1)


# ---------------------------------------------------------------------------
# Group 6 — Missing data returns (None, None)
# ---------------------------------------------------------------------------


def test_no_outcode_object_returns_none() -> None:
    # Given  payload with coordinates but no object containing an outcode key
    # When   _parse_coordinates is called
    # Then   (None, None) is returned
    html = _wrap_rsc({"coordinates": {"latitude": 51.5, "longitude": -0.1}})
    soup = BeautifulSoup(html, "html.parser")
    assert _parse_coordinates(soup) == (None, None)
