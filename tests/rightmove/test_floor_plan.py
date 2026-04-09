import pathlib

import dotenv
import pytest

from rightmove.floor_plan import FloorPlanSize, FloorPlanSizeExtractor

dotenv.load_dotenv()

_FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.mark.regression
@pytest.mark.parametrize(
    "filename, media_type, expected",
    [
        (
            "b07f2d1b8528840d56e98ea373b52eba.jpeg",
            "image/jpeg",
            FloorPlanSize(value=93.0, units="sq m"),
        ),
        (
            "8f99f96f54622f0cd8eeb15724086227.jpg",
            "image/jpeg",
            FloorPlanSize(value=65.0, units="sq m"),
        ),
        (
            "44554b8fd1d0d1296d0337d745133bff.jpg",
            "image/jpeg",
            FloorPlanSize(value=43.0, units="sq m"),
        ),
    ],
)
async def test_extract_floor_plan_size(
    filename: str,
    media_type: str,
    expected: FloorPlanSize,
) -> None:
    image_data = (_FIXTURES / filename).read_bytes()
    extractor = FloorPlanSizeExtractor()
    size = await extractor.extract(image_data, media_type=media_type)
    assert size == expected
