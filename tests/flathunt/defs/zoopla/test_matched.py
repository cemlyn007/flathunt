"""Tests for zoopla_matched_properties helpers.

Strategy:
- ``_to_final_property`` and ``_apply_size_filter`` are pure helpers that accept
  plain data; they are unit-tested directly without any Dagster context.
- The full asset is *not* tested end-to-end — it has async TfL journey calls and
  multiple resource dependencies that make end-to-end testing expensive.  The two
  extracted helpers cover all logic specific to this phase.
"""

import logging

from flathunt.defs.zoopla.matched import _apply_size_filter, _to_final_property
from zoopla.models import ZooplaListingDetail

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_listing(
    listing_id: str = "123456",
    floor_area_sqft: int | None = None,
    price_gbp: int | None = 2_000,
    latitude: float | None = 51.5,
    longitude: float | None = -0.1,
) -> ZooplaListingDetail:
    """Build a minimal but fully-valid ZooplaListingDetail for testing."""
    return ZooplaListingDetail(
        listing_id=listing_id,
        url=f"https://zoopla.co.uk/to-rent/details/{listing_id}",
        price_gbp=price_gbp,
        price_qualifier=None,
        address="1 Test Street, London, E1 1AA",
        property_type="flat",
        bedrooms=2,
        bathrooms=1,
        receptions=1,
        floor_area_sqft=floor_area_sqft,
        tenure="leasehold",
        service_charge=None,
        council_tax_band="C",
        ground_rent=None,
        ground_rent_review_date=None,
        chain_free=None,
        listing_condition=None,
        description="A test flat.",
        key_features=[],
        agent_name="Test Agent",
        agent_logo_url=None,
        image_urls=[
            "https://img.zoopla.co.uk/1.jpg",
            "https://img.zoopla.co.uk/2.jpg",
            "https://img.zoopla.co.uk/3.jpg",
        ],
        floorplan_urls=[],
        date_posted=None,
        latitude=latitude,
        longitude=longitude,
    )


# ---------------------------------------------------------------------------
# _to_final_property — unit tests
# ---------------------------------------------------------------------------


class TestToFinalPropertyStructuredFloorArea:
    def test_uses_structured_floor_area_when_present(self) -> None:
        """Structured floor_area_sqft takes priority; extractions are ignored."""
        detail = _make_listing("111", floor_area_sqft=637)
        result = _to_final_property(detail, [], {})

        assert result.display_size == "637 sq. ft."
        # 637 * 0.092903 ≈ 59.18 → int() truncates to 59 → float(59) = 59.0
        assert result.extracted_sqm == 59.0
        assert result.extracted_sqm_breakdown is None


class TestToFinalPropertyFallbackToExtractedSqm:
    def test_falls_back_to_extracted_sqm_when_structured_missing(self) -> None:
        """When floor_area_sqft is None and extractions has a total, use it."""
        detail = _make_listing("222", floor_area_sqft=None)
        extractions: dict[str, tuple[float | None, str | None]] = {"222": (59.0, None)}
        result = _to_final_property(detail, [], extractions)

        assert result.display_size == "59 sqm"
        assert result.extracted_sqm == 59.0
        assert result.extracted_sqm_breakdown is None


class TestToFinalPropertyExtractedBreakdownPassedThrough:
    def test_extracted_sqm_breakdown_passed_through(self) -> None:
        """When extraction has only a breakdown (no total), breakdown is passed through."""
        detail = _make_listing("333", floor_area_sqft=None)
        extractions: dict[str, tuple[float | None, str | None]] = {
            "333": (None, "30.0,35.0")
        }
        result = _to_final_property(detail, [], extractions)

        assert result.extracted_sqm is None
        assert result.display_size is None
        assert result.extracted_sqm_breakdown == "30.0,35.0"


class TestToFinalPropertyBothTotalAndBreakdown:
    def test_extracted_sqm_with_both_total_and_breakdown(self) -> None:
        """When extraction has both total and breakdown, both are set on the result."""
        detail = _make_listing("444", floor_area_sqft=None)
        extractions: dict[str, tuple[float | None, str | None]] = {
            "444": (80.0, "40.0,40.0")
        }
        result = _to_final_property(detail, [], extractions)

        assert result.extracted_sqm == 80.0
        assert result.display_size == "80 sqm"
        assert result.extracted_sqm_breakdown == "40.0,40.0"


class TestToFinalPropertyNoSizeDataAnywhere:
    def test_no_size_data_anywhere_returns_none(self) -> None:
        """When floor_area_sqft is None and listing absent from extractions, size fields are None."""
        detail = _make_listing("555", floor_area_sqft=None)
        result = _to_final_property(detail, [], {})

        assert result.extracted_sqm is None
        assert result.display_size is None
        assert result.extracted_sqm_breakdown is None


class TestToFinalPropertyStructuredWinsOverExtracted:
    def test_extracted_size_ignored_when_structured_size_present(self) -> None:
        """Structured size wins; extraction is not consulted when floor_area_sqft is set."""
        detail = _make_listing("666", floor_area_sqft=637)
        extractions: dict[str, tuple[float | None, str | None]] = {
            "666": (80.0, "40.0,40.0")
        }
        result = _to_final_property(detail, [], extractions)

        # Structured data wins; extracted values from the dict must not appear.
        assert result.display_size == "637 sq. ft."
        assert result.extracted_sqm == 59.0
        assert result.extracted_sqm_breakdown is None


# ---------------------------------------------------------------------------
# _apply_size_filter — unit tests
# ---------------------------------------------------------------------------


class TestSizeFilterKeepsUnknownSizeListings:
    def test_size_filter_keeps_unknown_size_listings(self) -> None:
        """A listing with no structured size and no extraction entry is kept."""
        detail = _make_listing("aaa", floor_area_sqft=None)
        result = _apply_size_filter([detail], {}, min_square_meters=60.0, log=logger)

        assert result == [detail]


class TestSizeFilterUsesExtractedSqmWhenStructuredMissing:
    def test_size_filter_keeps_when_extracted_sqm_above_minimum(self) -> None:
        """Listing with extracted size above minimum is kept."""
        detail = _make_listing("bbb", floor_area_sqft=None)
        extractions: dict[str, tuple[float | None, str | None]] = {"bbb": (70.0, None)}
        result = _apply_size_filter(
            [detail], extractions, min_square_meters=60.0, log=logger
        )

        assert result == [detail]

    def test_size_filter_excludes_when_extracted_sqm_below_minimum(self) -> None:
        """Listing with extracted size below minimum is excluded."""
        detail = _make_listing("ccc", floor_area_sqft=None)
        extractions: dict[str, tuple[float | None, str | None]] = {"ccc": (50.0, None)}
        result = _apply_size_filter(
            [detail], extractions, min_square_meters=60.0, log=logger
        )

        assert result == []


class TestSizeFilterPrefersStructuredOverExtracted:
    def test_size_filter_prefers_structured_over_extracted(self) -> None:
        """When both structured and extracted data are available, structured is used.

        637 sq ft ≈ 59.2 sqm — below a 60 sqm threshold.  The extracted value of
        80 sqm would pass, but structured data must win.
        """
        detail = _make_listing("ddd", floor_area_sqft=637)
        extractions: dict[str, tuple[float | None, str | None]] = {"ddd": (80.0, None)}
        result = _apply_size_filter(
            [detail], extractions, min_square_meters=60.0, log=logger
        )

        # Structured sqm ≈ 59.18 < 60; listing should be excluded.
        assert result == []


class TestSizeFilterKeepsWhenExtractionIsNoneNone:
    def test_size_filter_keeps_when_extraction_is_none_none(self) -> None:
        """Extraction returning (None, None) is treated as unknown size — listing kept."""
        detail = _make_listing("eee", floor_area_sqft=None)
        extractions: dict[str, tuple[float | None, str | None]] = {"eee": (None, None)}
        result = _apply_size_filter(
            [detail], extractions, min_square_meters=60.0, log=logger
        )

        assert result == [detail]


class TestSizeFilterBelowThresholdStructuredExcludes:
    def test_size_filter_with_below_threshold_structured_size_excludes(self) -> None:
        """Regression guard: pre-existing behaviour — structured size below min is excluded."""
        # 500 sq ft * 0.092903 ≈ 46.45 sqm, well below 60 sqm minimum.
        detail = _make_listing("fff", floor_area_sqft=500)
        result = _apply_size_filter([detail], {}, min_square_meters=60.0, log=logger)

        assert result == []
