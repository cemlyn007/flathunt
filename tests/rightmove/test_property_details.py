from pathlib import Path

import pytest

from rightmove.property_details import parse_property_details

_FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def property_details_html() -> str:
    return (_FIXTURES / "property_details.html").read_text(encoding="utf-8")


@pytest.fixture
def property_133551089_html() -> str:
    return (_FIXTURES / "property_details_133551089.html").read_text(encoding="utf-8")


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
