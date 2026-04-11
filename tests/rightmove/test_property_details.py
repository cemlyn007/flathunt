from pathlib import Path

import pytest

from rightmove.property_details import parse_property_details

_FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def property_details_html() -> str:
    return (_FIXTURES / "property_details.html").read_text(encoding="utf-8")


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
