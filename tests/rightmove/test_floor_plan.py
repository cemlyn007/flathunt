import pathlib

import dotenv
import pytest

from rightmove.floor_plan import (
    FloorPlanExtraction,
    FloorPlanSizeExtractor,
)

dotenv.load_dotenv()

_FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.mark.regression
@pytest.mark.parametrize(
    "filename, media_type, expected",
    [
        (
            "b07f2d1b8528840d56e98ea373b52eba.jpeg",
            "image/jpeg",
            FloorPlanExtraction(total=93.0, units="sq m"),
        ),
        (
            "8f99f96f54622f0cd8eeb15724086227.jpg",
            "image/jpeg",
            FloorPlanExtraction(total=65.0, units="sq m"),
        ),
        (
            "44554b8fd1d0d1296d0337d745133bff.jpg",
            "image/jpeg",
            FloorPlanExtraction(total=43.0, units="sq m"),
        ),
    ],
)
async def test_extract_floor_plan_size(
    filename: str,
    media_type: str,
    expected: FloorPlanExtraction,
) -> None:
    image_data = (_FIXTURES / filename).read_bytes()
    extractor = FloorPlanSizeExtractor()
    size = await extractor.extract(image_data, media_type=media_type)
    assert size == expected


def test_floor_plan_extraction_is_empty_all_none() -> None:
    """Test that is_empty() returns True when all fields are None."""
    extraction = FloorPlanExtraction(total=None, breakdown=None, units=None)
    assert extraction.is_empty() is True


def test_floor_plan_extraction_is_empty_false_with_total() -> None:
    """Test that is_empty() returns False when total is present."""
    extraction = FloorPlanExtraction(total=93.0, breakdown=None, units="sq m")
    assert extraction.is_empty() is False


def test_floor_plan_extraction_is_empty_false_with_breakdown() -> None:
    """Test that is_empty() returns False when breakdown is present."""
    extraction = FloorPlanExtraction(total=None, breakdown=[45.0, 47.0], units="sq m")
    assert extraction.is_empty() is False


def test_floor_plan_extraction_get_total_sqm_empty() -> None:
    """Test that get_total_sqm() returns None for empty extraction."""
    extraction = FloorPlanExtraction(total=None, breakdown=None, units=None)
    assert extraction.get_total_sqm() is None


def test_floor_plan_extraction_get_breakdown_csv_empty() -> None:
    """Test that get_breakdown_csv() returns None for empty extraction."""
    extraction = FloorPlanExtraction(total=None, breakdown=None, units=None)
    assert extraction.get_breakdown_csv() is None


def test_floor_plan_extraction_breakdown_only_sqm() -> None:
    """Test breakdown-only extraction with sq m units returns max value."""
    extraction = FloorPlanExtraction(
        total=None, breakdown=[45.0, 47.0, 33.0], units="sq m"
    )
    assert extraction.get_total_sqm() == 47.0
    assert extraction.get_breakdown_csv() == "45.0,47.0,33.0"


def test_floor_plan_extraction_breakdown_only_sqft() -> None:
    """Test breakdown-only extraction with sq ft units converts to sqm."""
    extraction = FloorPlanExtraction(
        total=None,
        breakdown=[500.0],  # ~46.45 sqm
        units="sq ft",
    )
    # max(breakdown) = 500, converted: 500 * 0.09290304 = 46.45
    total_sqm = extraction.get_total_sqm()
    assert total_sqm is not None and abs(total_sqm - 46.45152) < 0.01


def test_floor_plan_extraction_breakdown_only_no_units_returns_none() -> None:
    """Test that breakdown-only with units=None returns None (edge case).

    This scenario shouldn't occur if the prompt is honored (breakdown should
    always have units), but we ensure graceful handling by returning None
    when attempting to call get_total_sqm() on such malformed data.
    """
    extraction = FloorPlanExtraction(total=None, breakdown=[45.0, 47.0], units=None)
    # get_total_sqm returns None for malformed extraction (has data but no units)
    assert extraction.get_total_sqm() is None
