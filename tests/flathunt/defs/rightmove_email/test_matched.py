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


def _make_search_criteria(min_square_meters: float = 30.0) -> SearchCriteriaResource:
    return SearchCriteriaResource(
        min_budget=100_000,
        max_budget=900_000,
        min_square_meters=min_square_meters,
        has_floorplans=False,
        has_images=False,
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
) -> list[FinalProperty]:
    cache = _make_cache_mock(tmp_path)
    search_criteria = _make_search_criteria(min_square_meters=min_sqm)
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
