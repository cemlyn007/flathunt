"""Tests for rightmove_email_matched_properties — merge + size filter + matches DB.

Strategy:
- Provides pre-built ``FinalProperty`` candidates (as produced by the candidates
  asset) and ``MatchedProperty`` ids (as produced by the matched_ids asset).
- Exercises the merge of ``ExtractedAttributes`` into the candidate ``FinalProperty``.
- Exercises the null-safe size filter (display_size takes precedence, then
  extracted_sqm; unknown size → KEPT).
- Exercises that matched property IDs are written to the SQLite matches DB.

No real TfL/Anthropic calls; no real cache is required.
"""

import sqlite3
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import dagster as dg

from flathunt.anthropic_extraction import (
    ExtractedAttributes,
    ExtractedPropertyInfo,
    FloorPlanResult,
)
from flathunt.defs.resources import SearchCriteriaResource
from flathunt.defs.rightmove_email.matched import rightmove_email_matched_properties
from flathunt.models import FinalProperty, MatchedProperty
from rightmove.models import Price
from tests.flathunt.defs.gate_helpers import drain_gate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_search_criteria(
    min_square_meters: float = 30.0, exclude_below_ground: bool = True
) -> SearchCriteriaResource:
    return SearchCriteriaResource(
        min_budget=100_000,
        max_budget=900_000,
        min_square_meters=min_square_meters,
        has_floorplans=False,
        has_images=False,
        exclude_below_ground=exclude_below_ground,
    )


def _make_cache_mock(tmp_path: Path) -> MagicMock:
    mock = MagicMock()
    mock.data_dir = str(tmp_path)
    return mock


def _base_candidate(prop_id: int = 1) -> FinalProperty:
    return FinalProperty(
        id=prop_id,
        source="rightmove",
        display_address="x",
        price=Price(amount=500_000, frequency="static"),
        bedrooms=None,
        bathrooms=None,
        council_tax_band=None,
        tenure_type=None,
        display_size=None,
        extracted_sqm=None,
    )


def _run_asset(
    matched_ids: list[MatchedProperty],
    candidates: list[FinalProperty],
    extracted: dict[str, ExtractedAttributes],
    tmp_path: Path,
    min_sqm: float = 30.0,
    exclude_below_ground: bool = True,
) -> list[FinalProperty]:
    cache = _make_cache_mock(tmp_path)
    search_criteria = _make_search_criteria(
        min_square_meters=min_sqm, exclude_below_ground=exclude_below_ground
    )
    context = dg.build_asset_context()
    value, _ = drain_gate(
        rightmove_email_matched_properties(
            context=context,
            search_criteria=search_criteria,
            cache=cache,
            rightmove_email_matched_ids=matched_ids,
            rightmove_email_candidate_properties=candidates,
            rightmove_email_extracted_attributes=extracted,
        )
    )
    return cast(list[FinalProperty], value)


# ---------------------------------------------------------------------------
# Merge: extracted attributes are applied to the candidate FinalProperty
# ---------------------------------------------------------------------------


class TestMerge:
    def test_merge_applies_extracted_attributes(self, tmp_path: Path) -> None:
        """Extracted floor_plan and description fields are merged into the candidate."""
        candidate = _base_candidate(prop_id=1)
        matched_ids = [MatchedProperty(property_id=1, commute_durations=[20])]
        extracted = {
            "1": ExtractedAttributes(
                floor_plan=FloorPlanResult(total_sqm=70.0),
                description=ExtractedPropertyInfo(
                    council_tax_band="C",
                    bedrooms=2,
                    annual_service_charge=1200.0,
                ),
            )
        }

        result = _run_asset(matched_ids, [candidate], extracted, tmp_path)

        assert len(result) == 1
        fp = result[0]
        assert fp.extracted_sqm == 70.0
        assert fp.extracted_council_tax_band == "C"
        # bedrooms fallback-fill: candidate had None, extraction provided 2
        assert fp.bedrooms == 2
        assert fp.extracted_annual_service_charge == 1200.0
        assert fp.commute_durations == [20]


# ---------------------------------------------------------------------------
# Size filter: extracted_sqm below minimum → DROPPED
# ---------------------------------------------------------------------------


class TestSizeFilterDropsBelowMinimum:
    def test_extracted_sqm_below_minimum_dropped(self, tmp_path: Path) -> None:
        """A candidate whose only size signal is extracted_sqm < min is excluded."""
        candidate = _base_candidate(prop_id=2)
        matched_ids = [MatchedProperty(property_id=2, commute_durations=[])]
        extracted = {
            "2": ExtractedAttributes(
                floor_plan=FloorPlanResult(total_sqm=30.0),
            )
        }

        result = _run_asset(matched_ids, [candidate], extracted, tmp_path, min_sqm=50.0)

        assert len(result) == 0, (
            "Property with extracted_sqm=30.0 below min=50.0 must be excluded"
        )


# ---------------------------------------------------------------------------
# Size filter: unknown size → KEPT
# ---------------------------------------------------------------------------


class TestSizeFilterKeepsUnknown:
    def test_unknown_size_kept(self, tmp_path: Path) -> None:
        """A candidate with no size information at all is kept (null-safe)."""
        candidate = _base_candidate(prop_id=3)
        matched_ids = [MatchedProperty(property_id=3, commute_durations=[])]
        # Empty ExtractedAttributes — no floor_plan, no description
        extracted: dict[str, ExtractedAttributes] = {}

        result = _run_asset(matched_ids, [candidate], extracted, tmp_path, min_sqm=50.0)

        assert len(result) == 1, (
            "Property with no size information must be kept (null-safe)"
        )


# ---------------------------------------------------------------------------
# Matches DB: matched IDs are recorded in SQLite
# ---------------------------------------------------------------------------


class TestMatchesDB:
    def test_matched_ids_written_to_db(self, tmp_path: Path) -> None:
        """After the asset runs, the matched property IDs appear in the SQLite DB."""
        candidate = _base_candidate(prop_id=4)
        matched_ids = [MatchedProperty(property_id=4, commute_durations=[])]
        extracted: dict[str, ExtractedAttributes] = {}

        _run_asset(matched_ids, [candidate], extracted, tmp_path)

        db_path = tmp_path / "rightmove_email_matches.db"
        assert db_path.exists(), "rightmove_email_matches.db must be created"
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT property_id FROM email_matches WHERE property_id = ?", ("4",)
            ).fetchall()
        assert len(rows) == 1, "Property id 4 must be recorded in email_matches table"


# ---------------------------------------------------------------------------
# Below-ground filter
# ---------------------------------------------------------------------------


class TestBelowGroundFilter:
    def test_below_ground_excluded_by_default(self, tmp_path: Path) -> None:
        candidate = _base_candidate(prop_id=10)
        matched_ids = [MatchedProperty(property_id=10, commute_durations=[20])]
        extracted = {
            "10": ExtractedAttributes(
                floor_plan=FloorPlanResult(below_ground=True),
                description=ExtractedPropertyInfo(below_ground=True),
            )
        }
        result = _run_asset(matched_ids, [candidate], extracted, tmp_path)
        assert result == []

    def test_below_ground_kept_when_filter_disabled(self, tmp_path: Path) -> None:
        candidate = _base_candidate(prop_id=11)
        matched_ids = [MatchedProperty(property_id=11, commute_durations=[20])]
        extracted = {
            "11": ExtractedAttributes(
                floor_plan=FloorPlanResult(below_ground=True),
                description=ExtractedPropertyInfo(below_ground=True),
            )
        }
        result = _run_asset(
            matched_ids, [candidate], extracted, tmp_path, exclude_below_ground=False
        )
        assert len(result) == 1
        assert result[0].is_below_ground is True

    def test_conflicting_below_ground_kept(self, tmp_path: Path) -> None:
        candidate = _base_candidate(prop_id=12)
        matched_ids = [MatchedProperty(property_id=12, commute_durations=[20])]
        extracted = {
            "12": ExtractedAttributes(
                floor_plan=FloorPlanResult(below_ground=True),
                description=ExtractedPropertyInfo(below_ground=False),
            )
        }
        result = _run_asset(matched_ids, [candidate], extracted, tmp_path)
        assert len(result) == 1
        assert result[0].is_below_ground is None

    def test_confirmed_above_ground_kept(self, tmp_path: Path) -> None:
        candidate = _base_candidate(prop_id=13)
        matched_ids = [MatchedProperty(property_id=13, commute_durations=[20])]
        extracted = {
            "13": ExtractedAttributes(
                floor_plan=FloorPlanResult(below_ground=False),
            )
        }
        result = _run_asset(matched_ids, [candidate], extracted, tmp_path)
        assert len(result) == 1
        assert result[0].is_below_ground is False

    def test_below_ground_not_recorded_in_db(self, tmp_path: Path) -> None:
        candidate = _base_candidate(prop_id=14)
        matched_ids = [MatchedProperty(property_id=14, commute_durations=[20])]
        extracted = {
            "14": ExtractedAttributes(
                floor_plan=FloorPlanResult(below_ground=True),
                description=ExtractedPropertyInfo(below_ground=True),
            )
        }
        _run_asset(matched_ids, [candidate], extracted, tmp_path)

        db_path = tmp_path / "rightmove_email_matches.db"
        if not db_path.exists():
            return  # DB not created → property was definitely not recorded
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT property_id FROM email_matches WHERE property_id = ?", ("14",)
            ).fetchall()
        assert rows == [], "Below-ground property must not be written to matches DB"
