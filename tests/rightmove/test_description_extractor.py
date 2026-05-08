import pathlib

import dotenv
import pytest

from rightmove.description_extractor import (
    ExtractedPropertyInfo,
    PropertyDescriptionExtractor,
)
from rightmove.property_details import parse_property_details

dotenv.load_dotenv()

_FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def property_166537826_html() -> str:
    return (_FIXTURES / "property_details_166537826.html").read_text(encoding="utf-8")


def test_parse_description_present(property_166537826_html: str) -> None:
    details = parse_property_details(property_166537826_html)
    assert details.description is not None
    assert len(details.description) > 0


@pytest.fixture
def property_133551089_html() -> str:
    return (_FIXTURES / "property_details_133551089.html").read_text(encoding="utf-8")


@pytest.mark.regression
async def test_extract_property_info_from_description_when_api_returns_zero(
    property_133551089_html: str,
) -> None:
    # Rightmove's API returns yearsRemainingOnLease=0 for this property; the
    # description states "the lease has been extended to 170 years".
    details = parse_property_details(property_133551089_html)
    assert details.years_remaining_on_lease is None  # zero coerced to None
    assert details.description is not None

    extractor = PropertyDescriptionExtractor()
    info = await extractor.extract(details.description)

    assert info.years_remaining_on_lease == 170


@pytest.mark.regression
async def test_extract_property_info(property_166537826_html: str) -> None:
    details = parse_property_details(property_166537826_html)
    assert details.description is not None

    extractor = PropertyDescriptionExtractor()
    info = await extractor.extract(details.description)

    assert info == ExtractedPropertyInfo(
        tenure_type="LEASEHOLD",
        years_remaining_on_lease=109,
        annual_service_charge=4483.0,
        annual_ground_rent=100.0,
        council_tax_band="E",
    )
