import asyncio
from collections.abc import Coroutine
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import dagster as dg
import pytest

from flathunt.defs.zoopla.extracted_attributes import zoopla_extracted_attributes
from flathunt.models import MatchedProperty
from zoopla.models import ZooplaListingDetail


def _listing(
    listing_id,
    *,
    floor_area_sqft=None,
    floorplan_urls=None,
    description="A flat.",
    tenure="leasehold",
    bedrooms=2,
):
    return ZooplaListingDetail(
        listing_id=listing_id,
        url=f"https://z/{listing_id}",
        price_gbp=400_000,
        price_qualifier=None,
        address="1 St",
        property_type="flat",
        bedrooms=bedrooms,
        bathrooms=1,
        receptions=1,
        floor_area_sqft=floor_area_sqft,
        tenure=tenure,
        service_charge=None,
        council_tax_band=None,
        ground_rent=None,
        ground_rent_review_date=None,
        chain_free=None,
        listing_condition=None,
        description=description,
        key_features=[],
        agent_name=None,
        agent_logo_url=None,
        image_urls=[],
        floorplan_urls=floorplan_urls or [],
        date_posted=None,
        latitude=51.5,
        longitude=-0.1,
    )


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


def _run(listings, batch_results, tmp_path, *, expect_submit=True):
    cache = MagicMock()
    cache.data_dir = str(tmp_path)
    matched = [
        MatchedProperty(property_id=int(listing.listing_id), commute_durations=[])
        for listing in listings
    ]
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
                zoopla_extracted_attributes(
                    context=dg.build_asset_context(),
                    cache=cache,
                    zoopla_matched_ids=matched,
                    zoopla_candidate_properties=listings,
                ),
            )
        )
        if not expect_submit:
            sub.assert_not_called()
        return out


class TestZooplaExtractedAttributes:
    def test_floor_plan_and_description(self, tmp_path):
        listing = _listing("10001", floorplan_urls=["http://x/fp.jpg"])
        results = [
            _fake_result("fp_10001", json_text='{"total":59.0,"units":"sq m"}'),
            _fake_result(
                "desc_10001", json_text='{"council_tax_band":"C","bedrooms":2}'
            ),
        ]
        out = _run([listing], results, tmp_path)
        assert out["10001"].floor_plan.total_sqm == pytest.approx(59.0)
        assert out["10001"].description.council_tax_band == "C"

    def test_known_floor_area_skips_floor_plan_request_but_still_description(
        self, tmp_path
    ):
        listing = _listing(
            "10001", floor_area_sqft=637, floorplan_urls=["http://x/fp.jpg"]
        )
        out = _run(
            [listing],
            [_fake_result("desc_10001", json_text='{"bedrooms":2}')],
            tmp_path,
        )
        assert out["10001"].floor_plan is None
        assert out["10001"].description.bedrooms == 2

    def test_no_description_no_floorplans_means_no_submit(self, tmp_path):
        listing = _listing(
            "10001", floor_area_sqft=637, floorplan_urls=[], description=None
        )
        out = _run([listing], [], tmp_path, expect_submit=False)
        assert out["10001"].floor_plan is None and out["10001"].description is None
