"""Tests for listing coordinate extraction from Zoopla listing pages."""

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
# Group 2 — Nested shape: location with coordinates child + uprn sibling
# ---------------------------------------------------------------------------


def test_nested_coordinates_under_location_are_extracted() -> None:
    # Given  an object with nested coordinates and a sibling uprn key (current shape
    #        emitted by Zoopla under analyticsEcommerce.location)
    # When   _parse_coordinates is called
    # Then   latitude and longitude are pulled from the nested coordinates dict
    html = _wrap_rsc({
        "location": {
            "postalCode": "EC1V 7DX",
            "coordinates": {"latitude": 51.5, "longitude": -0.1},
            "uprn": "5300101867",
        }
    })
    soup = BeautifulSoup(html, "html.parser")
    assert _parse_coordinates(soup) == (51.5, -0.1)


# ---------------------------------------------------------------------------
# Group 3 — Flat shape: latitude/longitude as siblings of uprn
# ---------------------------------------------------------------------------


def test_flat_coordinates_alongside_uprn_are_extracted() -> None:
    # Given  an object with flat latitude/longitude alongside uprn (alternate
    #        shape Zoopla emits inside the address payload)
    # When   _parse_coordinates is called
    # Then   the flat fields are returned
    html = _wrap_rsc({
        "address": {
            "fullAddress": "1 Test Street, London",
            "latitude": 52.0,
            "longitude": -0.2,
            "postcode": "EC1V 7DX",
            "uprn": "1234567890",
        }
    })
    soup = BeautifulSoup(html, "html.parser")
    assert _parse_coordinates(soup) == (52.0, -0.2)


# ---------------------------------------------------------------------------
# Group 4 — EV charging stations are filtered out by uprn requirement
# ---------------------------------------------------------------------------


def test_ev_station_coordinates_without_uprn_are_ignored() -> None:
    # Given  payload contains a coordinates object without uprn (EV station shape)
    #        and a separate object with both uprn and listing coordinates
    # When   _parse_coordinates is called
    # Then   the listing coordinates are returned, not the EV station's
    html = _wrap_rsc([
        {
            "name": "EV Station",
            "postcode": "EC1V 3QU",
            "coordinates": {"latitude": 51.526651, "longitude": -0.099756},
        },
        {
            "location": {
                "coordinates": {"latitude": 51.5, "longitude": -0.1},
                "uprn": "5300101867",
            }
        },
    ])
    soup = BeautifulSoup(html, "html.parser")
    assert _parse_coordinates(soup) == (51.5, -0.1)


# ---------------------------------------------------------------------------
# Group 5 — Missing data returns (None, None)
# ---------------------------------------------------------------------------


def test_no_uprn_object_returns_none() -> None:
    # Given  payload with coordinates but no object containing a uprn key
    # When   _parse_coordinates is called
    # Then   (None, None) is returned
    html = _wrap_rsc({"coordinates": {"latitude": 51.5, "longitude": -0.1}})
    soup = BeautifulSoup(html, "html.parser")
    assert _parse_coordinates(soup) == (None, None)
