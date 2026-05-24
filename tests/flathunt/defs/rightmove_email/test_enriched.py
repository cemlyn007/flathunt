import asyncio
from typing import Any, cast

import pytest

import rightmove.models
from flathunt.cache import ModelCache
from flathunt.defs.rightmove_email.enriched import _extract_sizes, _to_final_property
from rightmove.email_models import RightmoveProperty
from rightmove.floor_plan import FloorPlanSizeExtractor


def _details(**overrides: Any) -> rightmove.models.PropertyDetails:
    base: dict[str, Any] = {
        "id": "1",
        "livingCosts": {"councilTaxExempt": False, "councilTaxIncluded": False},
    }
    base.update(overrides)
    return rightmove.models.PropertyDetails.model_validate(base)


def test_to_final_property_sets_beds_baths_and_api_size() -> None:
    details = _details(
        bedrooms=2,
        bathrooms=2,
        sizings=[{"unit": "sqm", "minimumSize": 82, "maximumSize": 82}],
    )
    fp = _to_final_property("123", "1 Test St", 500000, details)
    assert fp.bedrooms == 2
    assert fp.bathrooms == 2
    assert fp.display_size == "82 sqm"
    assert fp.extracted_sqm is None


def test_to_final_property_uses_extracted_sqm_when_no_api_size() -> None:
    details = _details(bedrooms=3, bathrooms=1, sizings=[])
    fp = _to_final_property("124", "2 Test St", None, details, extracted_sqm=70.0)
    assert fp.bedrooms == 3
    assert fp.bathrooms == 1
    assert fp.display_size is None
    assert fp.extracted_sqm == pytest.approx(70.0)


def test_to_final_property_blank_when_details_missing() -> None:
    fp = _to_final_property("125", None, None, None)
    assert fp.bedrooms is None
    assert fp.bathrooms is None
    assert fp.display_size is None
    assert fp.extracted_sqm is None


def _prop(listing_id: str) -> RightmoveProperty:
    return RightmoveProperty(
        listing_id=listing_id,
        url=f"/properties/{listing_id}",
        image_url=None,
        price_gbp=500000,
        price_text="£500,000",
        price_qualifier=None,
        is_reduced=False,
        property_type=None,
        address="1 Test St",
        marketed_by=None,
        agent_phone=None,
        photo_count=None,
        floorplan_count=None,
    )


def _fp_cache(tmp_path) -> ModelCache[tuple[float | None, str | None]]:
    return ModelCache(tuple[float | None, str | None], tmp_path / "fp.db")


def test_extract_sizes_prefers_api_and_skips_extraction(tmp_path) -> None:
    prop = _prop("100")
    details = _details(
        id="100", sizings=[{"unit": "sqm", "minimumSize": 90, "maximumSize": 90}]
    )
    extracted, counts = asyncio.run(
        _extract_sizes(
            [prop],
            {"100": details},
            _fp_cache(tmp_path),
            cast(FloorPlanSizeExtractor, object()),
            asyncio.Semaphore(1),
        )
    )
    assert extracted["100"] is None
    assert counts == {"size_from_api": 1, "size_from_floorplan": 0, "size_missing": 0}


def test_extract_sizes_falls_back_to_cached_floor_plan(tmp_path) -> None:
    prop = _prop("200")
    details = _details(id="200", sizings=[], floorplans=[{"url": "http://x/fp.png"}])
    cache = _fp_cache(tmp_path)
    cache.update([("200", (65.0, None))])  # pre-seed so no LLM call is made
    extracted, counts = asyncio.run(
        _extract_sizes(
            [prop],
            {"200": details},
            cache,
            cast(FloorPlanSizeExtractor, object()),
            asyncio.Semaphore(1),
        )
    )
    assert extracted["200"] == pytest.approx(65.0)
    assert counts == {"size_from_api": 0, "size_from_floorplan": 1, "size_missing": 0}


def test_extract_sizes_marks_missing_when_no_details(tmp_path) -> None:
    prop = _prop("300")
    extracted, counts = asyncio.run(
        _extract_sizes(
            [prop],
            {"300": None},
            _fp_cache(tmp_path),
            cast(FloorPlanSizeExtractor, object()),
            asyncio.Semaphore(1),
        )
    )
    assert extracted["300"] is None
    assert counts == {"size_from_api": 0, "size_from_floorplan": 0, "size_missing": 1}
