from pathlib import Path

import pytest

from rightmove.property_details import _resolve, parse_property_details

_FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def property_details_html() -> str:
    return (_FIXTURES / "property_details.html").read_text(encoding="utf-8")


@pytest.fixture
def property_133551089_html() -> str:
    return (_FIXTURES / "property_details_133551089.html").read_text(encoding="utf-8")


@pytest.fixture
def property_88235238_html() -> str:
    return (_FIXTURES / "property_details_88235238.html").read_text(encoding="utf-8")


def test_parse_property_id(property_details_html: str) -> None:
    details = parse_property_details(property_details_html)
    assert details.id == "168974183"


def test_parse_annual_service_charge(property_details_html: str) -> None:
    details = parse_property_details(property_details_html)
    assert details.living_costs.annual_service_charge == 7500


def test_parse_annual_ground_rent(property_details_html: str) -> None:
    details = parse_property_details(property_details_html)
    assert details.living_costs.annual_ground_rent == 350


def test_parse_council_tax_band(property_details_html: str) -> None:
    details = parse_property_details(property_details_html)
    assert details.living_costs.council_tax_band == "F"


def test_parse_tenure_type(property_details_html: str) -> None:
    details = parse_property_details(property_details_html)
    assert details.tenure_type == "LEASEHOLD"


def test_parse_years_remaining_on_lease(property_details_html: str) -> None:
    details = parse_property_details(property_details_html)
    assert details.years_remaining_on_lease == 974


def test_parse_years_remaining_on_lease_zero_treated_as_none(
    property_133551089_html: str,
) -> None:
    # Rightmove returns yearsRemainingOnLease=0 for this property, which is
    # invalid (the description states the lease was extended to 170 years).
    # Zero should be coerced to None so the LLM extractor is used instead.
    details = parse_property_details(property_133551089_html)
    assert details.years_remaining_on_lease is None


def test_parse_new_page_model_format(property_88235238_html: str) -> None:
    details = parse_property_details(property_88235238_html)
    assert details.id == "88235238"
    assert details.location is not None
    assert details.location.latitude == pytest.approx(51.435078)
    assert details.location.longitude == pytest.approx(-0.013478)
    assert details.living_costs.council_tax_band == "E"
    assert details.tenure_type == "FREEHOLD"
    assert details.years_remaining_on_lease is None
    assert len(details.floorplans) == 1


def test_resolve_handles_shared_references_and_primitives() -> None:
    # arr[0] root references arr[1] (a dict) twice; arr[1] holds a primitive
    # leaf at arr[2]. Verifies dedup via the cache and primitive passthrough.
    arr = [{"a": 1, "b": 1}, {"v": 2}, "leaf"]
    resolved = _resolve(0, arr, {})
    assert resolved == {"a": {"v": "leaf"}, "b": {"v": "leaf"}}
    assert resolved["a"] is resolved["b"]
