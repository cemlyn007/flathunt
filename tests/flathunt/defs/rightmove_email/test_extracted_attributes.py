import asyncio
from collections.abc import Coroutine
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import dagster as dg
import pytest

import rightmove.models
from flathunt.defs.rightmove_email.extracted_attributes import (
    rightmove_email_extracted_attributes,
)
from flathunt.models import MatchedProperty


def _details(
    *,
    id: str = "1",
    description: str | None = "A leasehold flat",
    floorplans: list[dict] | None = None,
    size_sqm: float | None = None,
    tenure_type: str | None = None,
    years_remaining_on_lease: int | None = None,
    bedrooms: int | None = None,
    bathrooms: int | None = None,
    annual_service_charge: float | None = None,
    annual_ground_rent: float | None = None,
    council_tax_band: str | None = None,
) -> rightmove.models.PropertyDetails:
    living_costs: dict[str, Any] = {
        "councilTaxExempt": False,
        "councilTaxIncluded": False,
    }
    if annual_service_charge is not None:
        living_costs["annualServiceCharge"] = annual_service_charge
    if annual_ground_rent is not None:
        living_costs["annualGroundRent"] = annual_ground_rent
    if council_tax_band is not None:
        living_costs["councilTaxBand"] = council_tax_band

    raw: dict[str, Any] = {
        "id": id,
        "livingCosts": living_costs,
    }
    if description is not None:
        raw["text"] = {"description": description}
    if floorplans is not None:
        raw["floorplans"] = floorplans
    if size_sqm is not None:
        raw["sizings"] = [
            {"unit": "sqm", "minimumSize": size_sqm, "maximumSize": size_sqm}
        ]
    if tenure_type is not None or years_remaining_on_lease is not None:
        raw["tenure"] = {
            "tenureType": tenure_type,
            "yearsRemainingOnLease": years_remaining_on_lease,
        }
    if bedrooms is not None:
        raw["bedrooms"] = bedrooms
    if bathrooms is not None:
        raw["bathrooms"] = bathrooms

    return rightmove.models.PropertyDetails.model_validate(raw)


def _fake_result(
    custom_id, result_type="succeeded", json_text='{"total":59.0,"units":"sq m"}'
):
    r = MagicMock()
    r.custom_id = custom_id
    r.result = MagicMock()
    r.result.type = result_type
    if result_type == "succeeded":
        b = MagicMock()
        b.text = json_text
        r.result.message = MagicMock()
        r.result.message.content = [b]
    return r


def _run(
    matched: list[MatchedProperty],
    details: dict[str, rightmove.models.PropertyDetailsFetchResult],
    batch_results: list,
    tmp_path,
    *,
    expect_submit: bool = True,
):
    cache = MagicMock()
    cache.data_dir = str(tmp_path)
    resp = MagicMock()
    resp.content = b"\xff\xd8\xff x"
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.get = AsyncMock(return_value=resp)
    with (
        patch("flathunt.anthropic_extraction.httpx.AsyncClient", return_value=client),
        patch("flathunt.anthropic_extraction.submit_batch", return_value="b1") as sub,
        patch(
            "flathunt.anthropic_extraction.poll_batch_completion",
            new_callable=AsyncMock,
        ),
        patch(
            "flathunt.anthropic_extraction._stream_batch_results",
            return_value=iter(batch_results),
        ),
    ):
        out = asyncio.run(
            cast(
                Coroutine[Any, Any, dict],
                rightmove_email_extracted_attributes(
                    context=dg.build_asset_context(),
                    cache=cache,
                    rightmove_email_matched_ids=matched,
                    rightmove_email_property_details=details,
                ),
            )
        )
        if not expect_submit:
            sub.assert_not_called()
        return out


class TestRightmoveEmailExtractedAttributes:
    def test_floor_plan_and_description(self, tmp_path):
        """Floor plan + description both extracted when size_sqm is unknown."""
        matched = [MatchedProperty(property_id=1, commute_durations=[20])]
        detail = _details(
            id="1",
            description="A leasehold flat",
            floorplans=[{"url": "http://x/fp.jpg"}],
            size_sqm=None,
            tenure_type=None,
            bedrooms=None,
            bathrooms=None,
        )
        results = [
            _fake_result("fp_1", json_text='{"total":59.0,"units":"sq m"}'),
            _fake_result("desc_1", json_text='{"council_tax_band":"C","bedrooms":2}'),
        ]
        out = _run(
            matched,
            {"1": rightmove.models.PropertyDetailsFetchResult(details=detail)},
            results,
            tmp_path,
        )
        assert out["1"].floor_plan.total_sqm == pytest.approx(59.0)
        assert out["1"].description.council_tax_band == "C"

    def test_known_size_sqm_skips_floor_plan_but_still_extracts_description(
        self, tmp_path
    ):
        """When size_sqm is already set, needs_floor_plan=False, so no fp_1 request."""
        matched = [MatchedProperty(property_id=1, commute_durations=[20])]
        detail = _details(
            id="1",
            description="A leasehold flat with 2 bedrooms",
            floorplans=[{"url": "http://x/fp.jpg"}],
            size_sqm=75.0,
            tenure_type=None,
            bedrooms=None,
            bathrooms=None,
        )
        results = [
            _fake_result("desc_1", json_text='{"bedrooms":2}'),
        ]
        out = _run(
            matched,
            {"1": rightmove.models.PropertyDetailsFetchResult(details=detail)},
            results,
            tmp_path,
            expect_submit=True,
        )
        assert out["1"].floor_plan is None
        assert out["1"].description.bedrooms == 2
