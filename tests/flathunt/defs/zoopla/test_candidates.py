"""Tests for zoopla_candidate_properties asset — null-safe filter behaviour.

Strategy:
- Use real ``SearchCriteriaResource`` with sensible defaults.
- Use ``dg.build_asset_context()`` for a lightweight Dagster context.
- Build a helper ``_listing(...)`` with sensible defaults, overriding per test.
- The isochrone polygon is constructed in BNG coordinates via ``shapely.geometry.box``;
  latitude/longitude points are verified against ``wgs84_to_bng`` to confirm
  inside/outside membership.

Core rule under test: a filter MUST NOT reject a listing because a needed value is
null/unknown.  Listings with no coordinates must be KEPT (commute-unknown path),
not excluded.
"""

from typing import cast

import dagster as dg
from shapely.geometry import Point, box

from flathunt.defs.resources import SearchCriteriaResource
from flathunt.defs.zoopla.candidates import zoopla_candidate_properties
from flathunt.geometry import wgs84_to_bng
from zoopla.models import ZooplaListingDetail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _listing(
    listing_id: str = "100001",
    price_gbp: int | None = 400_000,
    image_urls: list[str] | None = None,
    floor_area_sqft: int | None = None,
    latitude: float | None = 51.5,
    longitude: float | None = -0.1,
) -> ZooplaListingDetail:
    """Build a minimal but fully-valid ZooplaListingDetail for testing."""
    if image_urls is None:
        image_urls = [
            "https://img.zoopla.co.uk/1.jpg",
            "https://img.zoopla.co.uk/2.jpg",
            "https://img.zoopla.co.uk/3.jpg",
        ]
    return ZooplaListingDetail(
        listing_id=listing_id,
        url=f"https://zoopla.co.uk/for-sale/details/{listing_id}",
        price_gbp=price_gbp,
        price_qualifier=None,
        address="1 Test Street, London",
        property_type="flat",
        bedrooms=2,
        bathrooms=1,
        receptions=1,
        floor_area_sqft=floor_area_sqft,
        tenure="leasehold",
        service_charge=None,
        council_tax_band=None,
        ground_rent=None,
        ground_rent_review_date=None,
        chain_free=None,
        listing_condition=None,
        description="A lovely flat.",
        key_features=[],
        agent_name=None,
        agent_logo_url=None,
        image_urls=image_urls,
        floorplan_urls=[],
        date_posted=None,
        latitude=latitude,
        longitude=longitude,
    )


def _make_criteria(
    min_budget: float = 300_000,
    max_budget: float = 600_000,
    min_square_meters: float = 50.0,
    has_images: bool = True,
) -> SearchCriteriaResource:
    return SearchCriteriaResource(
        min_budget=min_budget,
        max_budget=max_budget,
        min_square_meters=min_square_meters,
        has_images=has_images,
        has_floorplans=False,
    )


# A BNG bounding box covering central London.
# London at lat=51.5, lon=-0.1 → BNG ≈ (531979, 179607) — inside.
# Scotland at lat=55.0, lon=-3.0 → BNG ≈ (336129, 567727) — outside.
_LONDON_POLY = box(500_000, 150_000, 560_000, 200_000)


def _run_asset(
    listings: list[ZooplaListingDetail],
    *,
    isochrone: list | None = None,
    criteria: SearchCriteriaResource | None = None,
) -> list[ZooplaListingDetail]:
    if criteria is None:
        criteria = _make_criteria()
    if isochrone is None:
        isochrone = [_LONDON_POLY]
    context = dg.build_asset_context()
    return cast(
        list[ZooplaListingDetail],
        zoopla_candidate_properties(
            context=context,
            search_criteria=criteria,
            zoopla_enriched_properties=listings,
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
# Filter 3 (isochrone) — null-safe coordinate tests
# ---------------------------------------------------------------------------


class TestListingWithoutCoordsIsKept:
    def test_listing_without_coords_is_kept(self) -> None:
        """A listing with latitude=None, longitude=None must pass the isochrone filter.

        The null-safe rule: missing coordinates means commute is unknown, so the
        listing should flow downstream rather than be discarded.
        """
        listing = _listing(latitude=None, longitude=None)
        result = _run_asset([listing])
        assert listing in result, (
            "Listing without coordinates must not be excluded by the isochrone filter"
        )


class TestListingWithCoordsOutsideIsochroneIsExcluded:
    def test_listing_with_coords_outside_isochrone_is_excluded(self) -> None:
        """A listing whose BNG point falls outside the isochrone polygon is excluded."""
        # Scotland — outside _LONDON_POLY
        listing = _listing(latitude=55.0, longitude=-3.0)
        result = _run_asset([listing])
        assert listing not in result, (
            "Listing outside the isochrone polygon must be excluded"
        )


class TestListingWithCoordsInsideIsochroneIsKept:
    def test_listing_with_coords_inside_isochrone_is_kept(self) -> None:
        """A listing whose BNG point falls inside the isochrone polygon is kept."""
        # Central London — inside _LONDON_POLY
        listing = _listing(latitude=51.5, longitude=-0.1)
        result = _run_asset([listing])
        assert listing in result, "Listing inside the isochrone polygon must be kept"


# ---------------------------------------------------------------------------
# Filter 1 (price) — null-safe test
# ---------------------------------------------------------------------------


class TestListingWithNullPriceIsKept:
    def test_listing_with_null_price_is_kept(self) -> None:
        """A listing with price_gbp=None must pass the price filter (unknown → keep).

        We cannot know if an unknown price is inside budget; the safe choice is
        to keep the listing for downstream evaluation.
        """
        listing = _listing(price_gbp=None, latitude=51.5, longitude=-0.1)
        result = _run_asset([listing])
        assert listing in result, (
            "Listing with null price must not be excluded by the price filter"
        )
