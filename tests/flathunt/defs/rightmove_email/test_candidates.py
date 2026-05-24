"""Tests for rightmove_email_candidate_properties asset — null-safe filter behaviour.

Strategy:
- Use real ``SearchCriteriaResource`` with sensible defaults.
- Use ``dg.build_asset_context()`` for a lightweight Dagster context.
- Build helpers ``_prop(...)`` and ``_alert(...)`` with sensible defaults.
- The isochrone polygon is constructed in BNG coordinates via ``shapely.geometry.box``;
  latitude/longitude points are verified against ``wgs84_to_bng`` to confirm
  inside/outside membership.

Core rule under test: a filter MUST NOT reject a property because a needed value is
null/unknown.  Properties with no coordinates must be KEPT (commute-unknown path),
not excluded.
"""

from datetime import datetime
from typing import cast

import dagster as dg
from shapely.geometry import Point, box

from flathunt.defs.resources import SearchCriteriaResource
from flathunt.defs.rightmove_email.candidates import (
    rightmove_email_candidate_properties,
)
from flathunt.geometry import wgs84_to_bng
from flathunt.models import FinalProperty
from rightmove.email_models import RightmoveProperty, RightmovePropertyAlert
from rightmove.models import Price

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rm_property(
    listing_id: str = "100001",
    photo_count: int | None = 5,
    floorplan_count: int | None = 1,
) -> RightmoveProperty:
    """Build a minimal RightmoveProperty for testing."""
    return RightmoveProperty(
        listing_id=listing_id,
        url=f"https://rightmove.co.uk/properties/{listing_id}",
        image_url=None,
        price_gbp=400_000,
        price_text="£400,000",
        price_qualifier=None,
        is_reduced=False,
        property_type="flat",
        address="1 Test Street, London",
        marketed_by=None,
        agent_phone=None,
        photo_count=photo_count,
        floorplan_count=floorplan_count,
    )


def _alert(
    *properties: RightmoveProperty,
) -> list[RightmovePropertyAlert]:
    """Wrap RightmoveProperty objects into a single alert list."""
    return [
        RightmovePropertyAlert(
            message_id="msg-001",
            subject="Rightmove Alert",
            received_at=datetime(2024, 1, 1, 12, 0, 0),
            properties=list(properties),
        )
    ]


def _prop(
    listing_id: str = "100001",
    price_amount: int | None = 400_000,
    latitude: float | None = 51.5,
    longitude: float | None = -0.1,
    display_size: str | None = None,
) -> FinalProperty:
    """Build a minimal FinalProperty for testing."""
    price = (
        Price(amount=price_amount, frequency="monthly", currency_code="GBP")
        if price_amount is not None
        else None
    )
    return FinalProperty(
        id=int(listing_id),
        display_address="1 Test Street, London",
        price=price,
        latitude=latitude,
        longitude=longitude,
        display_size=display_size,
    )


def _make_criteria(
    min_budget: float = 300_000,
    max_budget: float = 600_000,
    has_floorplans: bool = False,
    has_images: bool = True,
) -> SearchCriteriaResource:
    return SearchCriteriaResource(
        min_budget=min_budget,
        max_budget=max_budget,
        min_square_meters=50.0,
        has_images=has_images,
        has_floorplans=has_floorplans,
    )


# A BNG bounding box covering central London.
# London at lat=51.5, lon=-0.1 → BNG ≈ (531979, 179607) — inside.
# Scotland at lat=55.0, lon=-3.0 → BNG ≈ (336129, 567727) — outside.
_LONDON_POLY = box(500_000, 150_000, 560_000, 200_000)


def _run_asset(
    props: list[FinalProperty],
    alerts: list[RightmovePropertyAlert],
    *,
    isochrone: list | None = None,
    criteria: SearchCriteriaResource | None = None,
) -> list[FinalProperty]:
    if criteria is None:
        criteria = _make_criteria()
    if isochrone is None:
        isochrone = [_LONDON_POLY]
    context = dg.build_asset_context()
    return cast(
        list[FinalProperty],
        rightmove_email_candidate_properties(
            context=context,
            search_criteria=criteria,
            rightmove_property_alerts=alerts,
            rightmove_enriched_properties=props,
            isochrone_intersection=isochrone,
        ),
    )


# ---------------------------------------------------------------------------
# Geometry sanity: confirm inside/outside membership before writing tests
# ---------------------------------------------------------------------------


def test_geometry_sanity_inside() -> None:
    """London coordinates should fall inside the BNG polygon."""
    e, n = wgs84_to_bng(-0.1, 51.5)
    assert _LONDON_POLY.contains(Point(e, n)), (
        f"Expected ({e:.0f}, {n:.0f}) to be inside the test polygon"
    )


def test_geometry_sanity_outside() -> None:
    """Scotland coordinates should fall outside the BNG polygon."""
    e, n = wgs84_to_bng(-3.0, 55.0)
    assert not _LONDON_POLY.contains(Point(e, n)), (
        f"Expected ({e:.0f}, {n:.0f}) to be outside the test polygon"
    )


# ---------------------------------------------------------------------------
# Filter 1 (price) — null-safe tests
# ---------------------------------------------------------------------------


class TestNullPriceKept:
    def test_null_price_kept(self) -> None:
        """A FinalProperty with price=None must pass the price filter (unknown → keep).

        We cannot know if an unknown price is inside budget; the safe choice is
        to keep the property for downstream evaluation.
        """
        rm = _rm_property("200001")
        prop = _prop("200001", price_amount=None, latitude=51.5, longitude=-0.1)
        result = _run_asset([prop], _alert(rm))
        assert prop in result, (
            "Property with null price must not be excluded by the price filter"
        )


class TestPriceOutOfRangeExcluded:
    def test_price_out_of_range_excluded(self) -> None:
        """A property with a known price outside [min_budget, max_budget] is excluded."""
        rm = _rm_property("200002")
        prop = _prop("200002", price_amount=1_000_000, latitude=51.5, longitude=-0.1)
        criteria = _make_criteria(min_budget=300_000, max_budget=600_000)
        result = _run_asset([prop], _alert(rm), criteria=criteria)
        assert prop not in result, "Property with price outside budget must be excluded"


# ---------------------------------------------------------------------------
# Filter 3 (isochrone) — null-safe coordinate tests
# ---------------------------------------------------------------------------


class TestNoCoordsKept:
    def test_no_coords_kept(self) -> None:
        """A FinalProperty with latitude=None, longitude=None must pass the isochrone filter.

        The null-safe rule: missing coordinates means commute is unknown, so the
        property should flow downstream rather than be discarded.
        """
        rm = _rm_property("200003")
        prop = _prop("200003", latitude=None, longitude=None)
        result = _run_asset([prop], _alert(rm))
        assert prop in result, (
            "Property without coordinates must not be excluded by the isochrone filter"
        )


class TestCoordsOutsideIsochroneExcluded:
    def test_coords_outside_isochrone_excluded(self) -> None:
        """A property whose BNG point falls outside the isochrone polygon is excluded."""
        # Scotland — outside _LONDON_POLY
        rm = _rm_property("200004")
        prop = _prop("200004", latitude=55.0, longitude=-3.0)
        result = _run_asset([prop], _alert(rm))
        assert prop not in result, (
            "Property outside the isochrone polygon must be excluded"
        )


class TestCoordsInsideIsochroneKept:
    def test_coords_inside_isochrone_kept(self) -> None:
        """A property whose BNG point falls inside the isochrone polygon is kept."""
        # Central London — inside _LONDON_POLY
        rm = _rm_property("200005")
        prop = _prop("200005", latitude=51.5, longitude=-0.1)
        result = _run_asset([prop], _alert(rm))
        assert prop in result, "Property inside the isochrone polygon must be kept"


# ---------------------------------------------------------------------------
# Filter 2 (floorplans) — null-safe tests
# ---------------------------------------------------------------------------


class TestNullFloorplanCountKeptWhenHasFloorplans:
    def test_null_floorplan_count_kept_when_has_floorplans(self) -> None:
        """A property with floorplan_count=None must pass when has_floorplans=True.

        Unknown floorplan count cannot confirm absence of floorplans; the safe choice
        is to keep the property.
        """
        rm = _rm_property("200006", floorplan_count=None)
        prop = _prop("200006", latitude=51.5, longitude=-0.1)
        criteria = _make_criteria(has_floorplans=True)
        result = _run_asset([prop], _alert(rm), criteria=criteria)
        assert prop in result, (
            "Property with null floorplan_count must not be excluded when has_floorplans=True"
        )


class TestZeroFloorplanCountExcludedWhenHasFloorplans:
    def test_zero_floorplan_count_excluded_when_has_floorplans(self) -> None:
        """A property with floorplan_count=0 is excluded when has_floorplans=True."""
        rm = _rm_property("200007", floorplan_count=0)
        prop = _prop("200007", latitude=51.5, longitude=-0.1)
        criteria = _make_criteria(has_floorplans=True)
        result = _run_asset([prop], _alert(rm), criteria=criteria)
        assert prop not in result, (
            "Property with floorplan_count=0 must be excluded when has_floorplans=True"
        )


# ---------------------------------------------------------------------------
# Filter 3 (photos) — null-safe test
# ---------------------------------------------------------------------------


class TestNullPhotoCountKeptWhenHasImages:
    def test_null_photo_count_kept_when_has_images(self) -> None:
        """A property with photo_count=None must pass when has_images=True.

        Unknown photo count cannot confirm absence of images; the safe choice
        is to keep the property.
        """
        rm = _rm_property("200008", photo_count=None)
        prop = _prop("200008", latitude=51.5, longitude=-0.1)
        criteria = _make_criteria(has_images=True)
        result = _run_asset([prop], _alert(rm), criteria=criteria)
        assert prop in result, (
            "Property with null photo_count must not be excluded when has_images=True"
        )


# ---------------------------------------------------------------------------
# Filter 5 (structured size) — null-safe tests
# ---------------------------------------------------------------------------


class TestKnownTooSmallStructuredSizeExcluded:
    def test_known_too_small_structured_size_excluded(self) -> None:
        """A property with a known structured size below the minimum is excluded.

        "40 sqm" parses to 40.0 sqm; with min_square_meters=50 it must be rejected.
        """
        rm = _rm_property("200009")
        prop = _prop("200009", latitude=51.5, longitude=-0.1, display_size="40 sqm")
        criteria = _make_criteria()  # min_square_meters=50.0
        result = _run_asset([prop], _alert(rm), criteria=criteria)
        assert prop not in result, (
            "Property with known size below minimum must be excluded by the size filter"
        )


class TestUnknownSizeKept:
    def test_unknown_size_kept(self) -> None:
        """A property with display_size=None must pass the size filter (null-safe).

        Unknown size cannot confirm the property is too small; the safe choice
        is to keep the property for downstream evaluation.
        """
        rm = _rm_property("200010")
        prop = _prop("200010", latitude=51.5, longitude=-0.1, display_size=None)
        criteria = _make_criteria()  # min_square_meters=50.0
        result = _run_asset([prop], _alert(rm), criteria=criteria)
        assert prop in result, (
            "Property with null display_size must not be excluded by the size filter"
        )
