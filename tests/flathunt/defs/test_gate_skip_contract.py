"""Drift guard: every funnel gate must skip-with-observation on empty input.

The skip/observe block is inlined at each gate (per the spec), so this single
file is the consistency fence that stops the copies from diverging.
"""

from pathlib import Path
from unittest.mock import MagicMock

import dagster as dg

from flathunt.defs.resources import (
    QueriesResource,
    SearchCriteriaResource,
    TflResource,
)
from flathunt.defs.rightmove_email.candidates import (
    rightmove_email_candidate_properties,
)
from flathunt.defs.rightmove_email.matched import rightmove_email_matched_properties
from flathunt.defs.rightmove_email.matched_ids import rightmove_email_matched_ids
from flathunt.defs.rightmove_search.candidates import candidate_properties
from flathunt.defs.rightmove_search.matched import matched_property_ids
from flathunt.defs.rightmove_search.matched_properties import matched_properties
from flathunt.defs.zoopla.candidates import zoopla_candidate_properties
from flathunt.defs.zoopla.matched import zoopla_matched_properties
from flathunt.defs.zoopla.matched_ids import zoopla_matched_ids
from tests.flathunt.defs.gate_helpers import drain_gate


def _cache(tmp_path: Path) -> MagicMock:
    mock = MagicMock()
    mock.data_dir = str(tmp_path)
    return mock


def _queries() -> QueriesResource:
    return QueriesResource(queries=[{"lon": -0.1, "lat": 51.5, "max_duration": 30.0}])


def _tfl() -> TflResource:
    return TflResource(api_key="fake-api-key")  # type: ignore[call-arg]


def _criteria() -> SearchCriteriaResource:
    return SearchCriteriaResource(min_square_meters=50.0)


def test_rightmove_email_candidates_skips_when_empty() -> None:
    value, obs = drain_gate(
        rightmove_email_candidate_properties(
            context=dg.build_asset_context(),
            search_criteria=_criteria(),
            rightmove_property_alerts=[],
            rightmove_enriched_properties=[],
            isochrone_intersection=[],
        )
    )
    assert value == []
    assert len(obs) == 1
    assert obs[0].metadata["candidate_count"].value == 0


def test_rightmove_email_matched_ids_skips_when_empty(tmp_path: Path) -> None:
    value, obs = drain_gate(
        rightmove_email_matched_ids(
            context=dg.build_asset_context(),
            queries=_queries(),
            tfl_resource=_tfl(),
            cache=_cache(tmp_path),
            rightmove_email_candidate_properties=[],
        )
    )
    assert value == []
    assert len(obs) == 1
    assert obs[0].metadata["matched_count"].value == 0


def test_rightmove_email_matched_properties_skips_when_empty(tmp_path: Path) -> None:
    value, obs = drain_gate(
        rightmove_email_matched_properties(
            context=dg.build_asset_context(),
            search_criteria=_criteria(),
            cache=_cache(tmp_path),
            rightmove_email_matched_ids=[],
            rightmove_email_candidate_properties=[],
            rightmove_email_extracted_attributes={},
        )
    )
    assert value == []
    assert len(obs) == 1
    assert obs[0].metadata["final_count"].value == 0


def test_zoopla_candidates_skips_when_empty() -> None:
    value, obs = drain_gate(
        zoopla_candidate_properties(
            context=dg.build_asset_context(),
            search_criteria=_criteria(),
            zoopla_enriched_properties=[],
            isochrone_intersection=[],
        )
    )
    assert value == []
    assert len(obs) == 1
    assert obs[0].metadata["candidate_count"].value == 0


def test_zoopla_matched_ids_skips_when_empty(tmp_path: Path) -> None:
    value, obs = drain_gate(
        zoopla_matched_ids(
            context=dg.build_asset_context(),
            queries=_queries(),
            tfl_resource=_tfl(),
            cache=_cache(tmp_path),
            zoopla_candidate_properties=[],
        )
    )
    assert value == []
    assert len(obs) == 1
    assert obs[0].metadata["matched_count"].value == 0


def test_zoopla_matched_properties_skips_when_empty() -> None:
    value, obs = drain_gate(
        zoopla_matched_properties(
            context=dg.build_asset_context(),
            search_criteria=_criteria(),
            zoopla_matched_ids=[],
            zoopla_candidate_properties=[],
            zoopla_extracted_attributes={},
        )
    )
    assert value == []
    assert len(obs) == 1
    assert obs[0].metadata["matched_count"].value == 0


def test_rightmove_search_candidates_skips_when_isochrone_empty(
    tmp_path: Path,
) -> None:
    value, obs = drain_gate(
        candidate_properties(
            context=dg.build_asset_context(),
            search_criteria=_criteria(),
            cache=_cache(tmp_path),
            isochrone_intersection=[],
        )
    )
    assert value == []
    assert len(obs) == 1
    assert obs[0].metadata["property_count"].value == 0


def test_rightmove_search_matched_ids_skips_when_empty(tmp_path: Path) -> None:
    value, obs = drain_gate(
        matched_property_ids(
            context=dg.build_asset_context(),
            queries=_queries(),
            tfl_resource=_tfl(),
            cache=_cache(tmp_path),
            candidate_properties=[],
        )
    )
    assert value == []
    assert len(obs) == 1
    assert obs[0].metadata["matched_count"].value == 0


def test_rightmove_search_matched_properties_skips_when_empty() -> None:
    value, obs = drain_gate(
        matched_properties(
            context=dg.build_asset_context(),
            search_criteria=_criteria(),
            matched_property_ids=[],
            candidate_properties=[],
            rightmove_property_details={},
            extracted_attributes={},
        )
    )
    assert value == []
    assert len(obs) == 1
    assert obs[0].metadata["final_count"].value == 0
