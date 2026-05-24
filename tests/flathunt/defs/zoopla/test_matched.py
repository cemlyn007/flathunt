"""Tests for zoopla_matched_properties helpers.

Strategy:
- ``_to_final_property`` and ``_apply_size_filter`` are pure helpers that accept
  plain data; they are unit-tested directly without any Dagster context.
- The full asset is tested via ``zoopla_matched_properties`` for the merged
  ExtractedAttributes path (beds/baths fallback, extracted_* fields, size filter).
"""

import logging
from typing import cast

import dagster as dg

from flathunt.anthropic_extraction import (
    ExtractedAttributes,
    ExtractedPropertyInfo,
    FloorPlanResult,
)
from flathunt.defs.resources import SearchCriteriaResource
from flathunt.defs.zoopla.matched import (
    _apply_size_filter,
    _to_final_property,
    zoopla_matched_properties,
)
from flathunt.models import FinalProperty, MatchedProperty
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
    bedrooms: int | None = None,
    bathrooms: int | None = None,
    tenure: str | None = None,
    council_tax_band: str | None = None,
) -> ZooplaListingDetail:
    """Build a minimal but fully-valid ZooplaListingDetail for testing."""
    return ZooplaListingDetail(
        listing_id=listing_id,
        url=f"https://zoopla.co.uk/to-rent/details/{listing_id}",
        price_gbp=price_gbp,
        price_qualifier=None,
        address="1 Test Street, London, E1 1AA",
        property_type="flat",
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        receptions=1,
        floor_area_sqft=floor_area_sqft,
        tenure=tenure,
        service_charge=None,
        council_tax_band=council_tax_band,
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
        """Structured floor_area_sqft takes priority; attrs are ignored for size."""
        detail = _make_listing("111", floor_area_sqft=637)
        result = _to_final_property(detail, [], None)

        assert result.display_size == "637 sq. ft."
        # 637 * 0.092903 ≈ 59.18 → int() truncates to 59 → float(59) = 59.0
        assert result.extracted_sqm == 59.0
        assert result.extracted_sqm_breakdown is None


class TestToFinalPropertyFallbackToExtractedSqm:
    def test_falls_back_to_extracted_sqm_when_structured_missing(self) -> None:
        """When floor_area_sqft is None and attrs has a floor_plan total, use it."""
        detail = _make_listing("222", floor_area_sqft=None)
        attrs = ExtractedAttributes(floor_plan=FloorPlanResult(total_sqm=59.0))
        result = _to_final_property(detail, [], attrs)

        assert result.display_size == "59 sqm"
        assert result.extracted_sqm == 59.0
        assert result.extracted_sqm_breakdown is None


class TestToFinalPropertyExtractedBreakdownPassedThrough:
    def test_extracted_sqm_breakdown_passed_through(self) -> None:
        """When extraction has only a breakdown (no total), breakdown is passed through."""
        detail = _make_listing("333", floor_area_sqft=None)
        attrs = ExtractedAttributes(
            floor_plan=FloorPlanResult(total_sqm=None, breakdown_csv="30.0,35.0")
        )
        result = _to_final_property(detail, [], attrs)

        assert result.extracted_sqm is None
        assert result.display_size is None
        assert result.extracted_sqm_breakdown == "30.0,35.0"


class TestToFinalPropertyBothTotalAndBreakdown:
    def test_extracted_sqm_with_both_total_and_breakdown(self) -> None:
        """When extraction has both total and breakdown, both are set on the result."""
        detail = _make_listing("444", floor_area_sqft=None)
        attrs = ExtractedAttributes(
            floor_plan=FloorPlanResult(total_sqm=80.0, breakdown_csv="40.0,40.0")
        )
        result = _to_final_property(detail, [], attrs)

        assert result.extracted_sqm == 80.0
        assert result.display_size == "80 sqm"
        assert result.extracted_sqm_breakdown == "40.0,40.0"


class TestToFinalPropertyNoSizeDataAnywhere:
    def test_no_size_data_anywhere_returns_none(self) -> None:
        """When floor_area_sqft is None and attrs is None, size fields are None."""
        detail = _make_listing("555", floor_area_sqft=None)
        result = _to_final_property(detail, [], None)

        assert result.extracted_sqm is None
        assert result.display_size is None
        assert result.extracted_sqm_breakdown is None


class TestToFinalPropertyStructuredWinsOverExtracted:
    def test_extracted_size_ignored_when_structured_size_present(self) -> None:
        """Structured size wins; extraction is not consulted when floor_area_sqft is set."""
        detail = _make_listing("666", floor_area_sqft=637)
        attrs = ExtractedAttributes(
            floor_plan=FloorPlanResult(total_sqm=80.0, breakdown_csv="40.0,40.0")
        )
        result = _to_final_property(detail, [], attrs)

        # Structured data wins; extracted values from attrs must not appear.
        assert result.display_size == "637 sq. ft."
        assert result.extracted_sqm == 59.0
        assert result.extracted_sqm_breakdown is None


class TestToFinalPropertyExtractedAttributesMerge:
    def test_extracted_description_fields_populated(self) -> None:
        """extracted_* fields come from ExtractedAttributes.description."""
        detail = _make_listing(
            "777", floor_area_sqft=None, bedrooms=None, bathrooms=None
        )
        attrs = ExtractedAttributes(
            floor_plan=FloorPlanResult(total_sqm=70.0),
            description=ExtractedPropertyInfo(
                council_tax_band="C",
                bedrooms=2,
                annual_service_charge=1200.0,
                annual_ground_rent=150.0,
                tenure_type="LEASEHOLD",
                years_remaining_on_lease=85,
                bathrooms=1,
            ),
        )
        result = _to_final_property(detail, [], attrs)

        assert result.extracted_sqm == 70.0
        assert result.extracted_council_tax_band == "C"
        assert result.bedrooms == 2  # fallback-filled from desc (structured is None)
        assert result.bathrooms == 1  # fallback-filled from desc
        assert result.extracted_annual_service_charge == 1200.0
        assert result.extracted_annual_ground_rent == 150.0
        assert result.extracted_tenure_type == "LEASEHOLD"
        assert result.extracted_years_remaining_on_lease == 85

    def test_structured_bedrooms_wins_over_extracted(self) -> None:
        """If detail.bedrooms is set, it is used over desc.bedrooms."""
        detail = _make_listing("888", bedrooms=3, bathrooms=2)
        attrs = ExtractedAttributes(
            description=ExtractedPropertyInfo(bedrooms=1, bathrooms=1)
        )
        result = _to_final_property(detail, [], attrs)

        assert result.bedrooms == 3
        assert result.bathrooms == 2


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
        attrs = {"bbb": ExtractedAttributes(floor_plan=FloorPlanResult(total_sqm=70.0))}
        result = _apply_size_filter([detail], attrs, min_square_meters=60.0, log=logger)

        assert result == [detail]

    def test_size_filter_excludes_when_extracted_sqm_below_minimum(self) -> None:
        """Listing with extracted size below minimum is excluded."""
        detail = _make_listing("ccc", floor_area_sqft=None)
        attrs = {"ccc": ExtractedAttributes(floor_plan=FloorPlanResult(total_sqm=50.0))}
        result = _apply_size_filter([detail], attrs, min_square_meters=60.0, log=logger)

        assert result == []


class TestSizeFilterPrefersStructuredOverExtracted:
    def test_size_filter_prefers_structured_over_extracted(self) -> None:
        """When both structured and extracted data are available, structured is used.

        637 sq ft ≈ 59.2 sqm — below a 60 sqm threshold.  The extracted value of
        80 sqm would pass, but structured data must win.
        """
        detail = _make_listing("ddd", floor_area_sqft=637)
        attrs = {"ddd": ExtractedAttributes(floor_plan=FloorPlanResult(total_sqm=80.0))}
        result = _apply_size_filter([detail], attrs, min_square_meters=60.0, log=logger)

        # Structured sqm ≈ 59.18 < 60; listing should be excluded.
        assert result == []


class TestSizeFilterKeepsWhenExtractionIsEmpty:
    def test_size_filter_keeps_when_floor_plan_is_none(self) -> None:
        """Extraction with no floor_plan is treated as unknown size — listing kept."""
        detail = _make_listing("eee", floor_area_sqft=None)
        attrs = {"eee": ExtractedAttributes()}
        result = _apply_size_filter([detail], attrs, min_square_meters=60.0, log=logger)

        assert result == [detail]

    def test_size_filter_keeps_when_floor_plan_total_sqm_is_none(self) -> None:
        """Extraction with floor_plan but total_sqm=None is treated as unknown — kept."""
        detail = _make_listing("fff", floor_area_sqft=None)
        attrs = {"fff": ExtractedAttributes(floor_plan=FloorPlanResult(total_sqm=None))}
        result = _apply_size_filter([detail], attrs, min_square_meters=60.0, log=logger)

        assert result == [detail]


class TestSizeFilterBelowThresholdStructuredExcludes:
    def test_size_filter_with_below_threshold_structured_size_excludes(self) -> None:
        """Regression guard: pre-existing behaviour — structured size below min is excluded."""
        # 500 sq ft * 0.092903 ≈ 46.45 sqm, well below 60 sqm minimum.
        detail = _make_listing("ggg", floor_area_sqft=500)
        result = _apply_size_filter([detail], {}, min_square_meters=60.0, log=logger)

        assert result == []


# ---------------------------------------------------------------------------
# zoopla_matched_properties — asset-level tests using ExtractedAttributes
# ---------------------------------------------------------------------------


def _search_criteria(min_square_meters: float = 30.0) -> SearchCriteriaResource:
    return SearchCriteriaResource(min_square_meters=min_square_meters)


class TestZooplaMatchedPropertiesAsset:
    def test_extracted_attributes_merged_into_final_property(self) -> None:
        """Extracted ExtractedAttributes fields are merged into FinalProperty correctly.

        listing_id is "99001"; all structured detail fields (bedrooms, bathrooms,
        council_tax_band, tenure) are None so they must be filled from attrs.
        """
        listing_id = "99001"
        listing = _make_listing(
            listing_id,
            floor_area_sqft=None,
            bedrooms=None,
            bathrooms=None,
            tenure=None,
            council_tax_band=None,
        )
        matched_ids = [
            MatchedProperty(property_id=int(listing_id), commute_durations=[20])
        ]
        attrs: dict[str, ExtractedAttributes] = {
            listing_id: ExtractedAttributes(
                floor_plan=FloorPlanResult(total_sqm=70.0),
                description=ExtractedPropertyInfo(
                    council_tax_band="C",
                    bedrooms=2,
                    annual_service_charge=1200.0,
                ),
            )
        }

        results = cast(
            list[FinalProperty],
            zoopla_matched_properties(
                context=dg.build_asset_context(),
                search_criteria=_search_criteria(min_square_meters=30.0),
                zoopla_matched_ids=matched_ids,
                zoopla_candidate_properties=[listing],
                zoopla_extracted_attributes=attrs,
            ),
        )

        assert len(results) == 1
        prop = results[0]
        assert prop.extracted_sqm == 70.0
        assert prop.extracted_council_tax_band == "C"
        assert prop.bedrooms == 2  # fallback-filled from desc
        assert prop.extracted_annual_service_charge == 1200.0

    def test_size_filter_drops_listing_below_min(self) -> None:
        """A listing whose only size signal is extracted 30.0 sqm with min=50 is dropped."""
        listing_id = "99002"
        listing = _make_listing(listing_id, floor_area_sqft=None)
        matched_ids = [
            MatchedProperty(property_id=int(listing_id), commute_durations=[10])
        ]
        attrs: dict[str, ExtractedAttributes] = {
            listing_id: ExtractedAttributes(
                floor_plan=FloorPlanResult(total_sqm=30.0),
            )
        }

        results = cast(
            list[FinalProperty],
            zoopla_matched_properties(
                context=dg.build_asset_context(),
                search_criteria=_search_criteria(min_square_meters=50.0),
                zoopla_matched_ids=matched_ids,
                zoopla_candidate_properties=[listing],
                zoopla_extracted_attributes=attrs,
            ),
        )

        assert results == []

    def test_size_filter_keeps_listing_with_unknown_size(self) -> None:
        """A listing with no floor_area_sqft and empty ExtractedAttributes is kept (null-safe)."""
        listing_id = "99003"
        listing = _make_listing(listing_id, floor_area_sqft=None)
        matched_ids = [
            MatchedProperty(property_id=int(listing_id), commute_durations=[15])
        ]
        # Empty ExtractedAttributes — no size signal at all.
        attrs: dict[str, ExtractedAttributes] = {listing_id: ExtractedAttributes()}

        results = cast(
            list[FinalProperty],
            zoopla_matched_properties(
                context=dg.build_asset_context(),
                search_criteria=_search_criteria(min_square_meters=50.0),
                zoopla_matched_ids=matched_ids,
                zoopla_candidate_properties=[listing],
                zoopla_extracted_attributes=attrs,
            ),
        )

        assert len(results) == 1
