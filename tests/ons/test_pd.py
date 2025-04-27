from typing import Optional
import pytest
from ons.pd import Postcode


@pytest.mark.parametrize(
    "postcode, expected_outward, expected_inward, expected_area, expected_district, expected_sub_district, expected_sector, expected_unit",
    [
        ("A9 9AA", "A9", "9AA", "A", "A9", None, "A9 9", "AA"),
        ("A99 9AA", "A99", "9AA", "A", "A99", None, "A99 9", "AA"),
        ("AA9 9AA", "AA9", "9AA", "AA", "AA9", None, "AA9 9", "AA"),
        ("AA99 9AA", "AA99", "9AA", "AA", "AA99", None, "AA99 9", "AA"),
        ("SW1A 2AA", "SW1A", "2AA", "SW", "SW1", "SW1A", "SW1A 2", "AA"),
    ],
)
def test_postcode(
    postcode: str,
    expected_outward: str,
    expected_inward: str,
    expected_area: str,
    expected_district: str,
    expected_sub_district: Optional[str],
    expected_sector: str,
    expected_unit: str,
) -> None:
    pc = Postcode(postcode=postcode)
    assert pc.outward == expected_outward
    assert pc.inward == expected_inward
    assert pc.area == expected_area
    assert pc.district == expected_district
    assert pc.sub_district == expected_sub_district
    assert pc.sector == expected_sector
    assert pc.unit == expected_unit
