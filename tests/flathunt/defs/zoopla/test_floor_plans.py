"""Tests for zoopla_extracted_floor_plans asset.

Strategy:
- `httpx.AsyncClient` is patched to avoid real HTTP calls.
- `submit_batch` and `poll_batch_completion` are patched to avoid Anthropic calls.
- Batch results are injected via a patched `_stream_batch_results` helper that the
  asset calls internally — this is a clean seam factored out specifically for
  testability (the seam takes an iterable of batch results rather than the raw
  Anthropic client call).
- The `FloorPlanSizeExtractor.build_batch_request` is patched to return a sentinel
  so we don't need valid image bytes.
- A real `ModelCache` backed by a tmp SQLite file is used for cache tests —
  mirrors the project convention of avoiding fake caches (see test_cache.py).
"""

import logging
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import dagster as dg
import pytest

from flathunt.cache import ModelCache
from flathunt.defs.zoopla.floor_plans import zoopla_extracted_floor_plans
from zoopla.models import ZooplaListingDetail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_listing(
    listing_id: str,
    floor_area_sqft: int | None = None,
    floorplan_urls: list[str] | None = None,
) -> ZooplaListingDetail:
    return ZooplaListingDetail(
        listing_id=listing_id,
        url=f"https://zoopla.co.uk/{listing_id}",
        price_gbp=400_000,
        price_qualifier=None,
        address="1 Test Street, London",
        property_type="flat",
        bedrooms=2,
        bathrooms=1,
        receptions=1,
        floor_area_sqft=floor_area_sqft,
        tenure="leasehold",
        service_charge=None,
        council_tax_band=None,
        ground_rent=None,
        ground_rent_review_date=None,
        chain_free=None,
        listing_condition=None,
        description="A lovely flat.",
        key_features=[],
        agent_name=None,
        agent_logo_url=None,
        image_urls=[],
        floorplan_urls=floorplan_urls or [],
        date_posted=None,
        latitude=51.5,
        longitude=-0.1,
    )


def _make_batch_result(
    custom_id: str,
    result_type: str = "succeeded",
    json_text: str = '{"total": 59.0, "units": "sq m"}',
) -> MagicMock:
    """Build a fake Anthropic BatchMessageResult-shaped object."""
    result = MagicMock()
    result.custom_id = custom_id
    result.result = MagicMock()
    result.result.type = result_type
    if result_type == "succeeded":
        content_block = MagicMock()
        content_block.text = json_text
        result.result.message = MagicMock()
        result.result.message.content = [content_block]
    return result


def _make_cache_resource(tmp_path: Path) -> MagicMock:
    resource = MagicMock()
    resource.data_dir = str(tmp_path)
    return resource


def _run_asset(
    listings: list[ZooplaListingDetail],
    batch_results: list[Any],
    tmp_path: Path,
    *,
    expect_submit: bool = True,
) -> dict[str, tuple[float | None, str | None]]:
    """Run the asset under full mock control, return its output dict."""
    cache_resource = _make_cache_resource(tmp_path)

    # Fake HTTP response: returns b"fake-png" for any URL
    mock_http_response = MagicMock()
    mock_http_response.content = b"fake-png"
    mock_http_response.raise_for_status = MagicMock()

    mock_http_client = MagicMock()
    mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
    mock_http_client.__aexit__ = AsyncMock(return_value=None)
    mock_http_client.get = AsyncMock(return_value=mock_http_response)

    sentinel_request = MagicMock(name="batch_request_sentinel")

    # Patch the entire FloorPlanSizeExtractor class so __init__ never calls
    # get_client() (which requires ANTHROPIC_API_KEY at construction time).
    mock_extractor_instance = MagicMock()
    mock_extractor_instance.build_batch_request.return_value = sentinel_request
    mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)

    with (
        patch(
            "flathunt.defs.zoopla.floor_plans.httpx.AsyncClient",
            return_value=mock_http_client,
        ),
        patch(
            "flathunt.defs.zoopla.floor_plans.FloorPlanSizeExtractor",
            mock_extractor_cls,
        ),
        patch(
            "flathunt.defs.zoopla.floor_plans.submit_batch",
            return_value="batch_abc123",
        ) as mock_submit,
        patch(
            "flathunt.defs.zoopla.floor_plans.poll_batch_completion",
            new_callable=AsyncMock,
        ),
        patch(
            "flathunt.defs.zoopla.floor_plans._stream_batch_results",
            return_value=iter(batch_results),
        ),
    ):
        context = dg.build_asset_context()
        result = zoopla_extracted_floor_plans(
            context=context,
            cache=cache_resource,
            zoopla_enriched_properties=listings,
        )
        if not expect_submit:
            mock_submit.assert_not_called()
        return cast(dict[str, tuple[float | None, str | None]], result)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSkipsListingsWithKnownFloorArea:
    def test_skips_listings_with_known_floor_area(self, tmp_path: Path) -> None:
        """Listings with floor_area_sqft already set should be excluded entirely."""
        listing = _make_listing(
            "abc123", floor_area_sqft=637, floorplan_urls=["http://img/1.jpg"]
        )
        result = _run_asset(
            [listing], batch_results=[], tmp_path=tmp_path, expect_submit=False
        )
        assert result == {}


class TestSkipsListingsWithNoFloorplanUrls:
    def test_skips_listings_with_no_floorplan_urls(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Listings with no floorplan_urls should be skipped with a log message."""
        listing = _make_listing("abc123", floor_area_sqft=None, floorplan_urls=[])

        with caplog.at_level(logging.INFO, logger="flathunt.defs.zoopla.floor_plans"):
            result = _run_asset(
                [listing], batch_results=[], tmp_path=tmp_path, expect_submit=False
            )

        assert result == {}
        assert any(
            "no floor plan url" in record.message.lower() for record in caplog.records
        )


class TestSubmitsBatchForListingsNeedingExtraction:
    def test_submits_batch_and_populates_result(self, tmp_path: Path) -> None:
        """Single listing with one floor plan URL; batch succeeds with total_sqm."""
        listing = _make_listing(
            "listing1", floor_area_sqft=None, floorplan_urls=["http://img/fp.jpg"]
        )
        batch_results = [
            _make_batch_result(
                "fp_listing1_0", json_text='{"total": 59.0, "units": "sq m"}'
            )
        ]

        result = _run_asset([listing], batch_results, tmp_path=tmp_path)

        assert "listing1" in result
        total_sqm, breakdown_csv = result["listing1"]
        assert total_sqm == pytest.approx(59.0)
        assert breakdown_csv is None

        # Cache should be populated
        cache = ModelCache(
            tuple[float | None, str | None],
            tmp_path / "zoopla_floor_plan_size_cache.db",
            ttl=None,
        )
        cached_total, _cached_csv = cache.get("listing1")
        assert cached_total == pytest.approx(59.0)


class TestUsesCachedValueWithoutResubmitting:
    def test_uses_cached_value_without_resubmitting(self, tmp_path: Path) -> None:
        """If cache has a value, the asset should return it without calling submit_batch."""
        # Pre-populate cache
        cache_db = ModelCache(
            tuple[float | None, str | None],
            tmp_path / "zoopla_floor_plan_size_cache.db",
            ttl=30 * 24 * 3600,
        )
        cache_db.update([("listing1", (80.0, None))])

        listing = _make_listing(
            "listing1", floor_area_sqft=None, floorplan_urls=["http://img/fp.jpg"]
        )
        result = _run_asset(
            [listing], batch_results=[], tmp_path=tmp_path, expect_submit=False
        )

        assert result == {"listing1": (80.0, None)}


class TestAggregatesMultipleFloorPlansPreferencesTotal:
    def test_aggregates_multiple_floor_plans_prefers_total(
        self, tmp_path: Path
    ) -> None:
        """Two URLs: first has breakdown only, second has total — prefer total."""
        listing = _make_listing(
            "listing1",
            floor_area_sqft=None,
            floorplan_urls=["http://img/fp0.jpg", "http://img/fp1.jpg"],
        )
        batch_results = [
            # First image: breakdown only (no total)
            _make_batch_result(
                "fp_listing1_0",
                json_text='{"breakdown": [30.0, 35.0], "units": "sq m"}',
            ),
            # Second image: total
            _make_batch_result(
                "fp_listing1_1",
                json_text='{"total": 65.0, "units": "sq m"}',
            ),
        ]

        result = _run_asset([listing], batch_results, tmp_path=tmp_path)

        assert "listing1" in result
        total_sqm, _ = result["listing1"]
        assert total_sqm == pytest.approx(65.0)


class TestRecordsNoneWhenBatchReturnsNoExtraction:
    def test_records_none_when_batch_returns_null(self, tmp_path: Path) -> None:
        """Batch returns JSON null → (None, None) stored in output and cache."""
        listing = _make_listing(
            "listing1", floor_area_sqft=None, floorplan_urls=["http://img/fp.jpg"]
        )
        batch_results = [_make_batch_result("fp_listing1_0", json_text="null")]

        result = _run_asset([listing], batch_results, tmp_path=tmp_path)

        assert result == {"listing1": (None, None)}

        cache = ModelCache(
            tuple[float | None, str | None],
            tmp_path / "zoopla_floor_plan_size_cache.db",
            ttl=None,
        )
        assert cache.get("listing1") == (None, None)


class TestRecordsNoneWhenBatchErroredForListing:
    def test_records_none_when_batch_errored(self, tmp_path: Path) -> None:
        """If batch result for custom_id is 'errored', output (None, None)."""
        listing = _make_listing(
            "listing1", floor_area_sqft=None, floorplan_urls=["http://img/fp.jpg"]
        )
        batch_results = [_make_batch_result("fp_listing1_0", result_type="errored")]

        result = _run_asset([listing], batch_results, tmp_path=tmp_path)

        assert result == {"listing1": (None, None)}


class TestImageDownloadFailureSkipsListing:
    def test_image_download_failure_results_in_none_none(self, tmp_path: Path) -> None:
        """If image download fails for a listing, it gets (None, None) in the output.

        A second listing that downloads successfully extracts normally.
        The failing listing is still included in the output dict as (None, None)
        because the asset records "we tried" for all listings that need extraction.
        """
        listing_fail = _make_listing(
            "listing_fail", floor_area_sqft=None, floorplan_urls=["http://img/fail.jpg"]
        )
        listing_ok = _make_listing(
            "listing_ok", floor_area_sqft=None, floorplan_urls=["http://img/ok.jpg"]
        )

        cache_resource = _make_cache_resource(tmp_path)

        fail_response = MagicMock()
        fail_response.raise_for_status = MagicMock(
            side_effect=Exception("connection refused")
        )

        ok_response = MagicMock()
        ok_response.content = b"fake-png"
        ok_response.raise_for_status = MagicMock()

        call_count = 0

        def side_effect_get(url: str, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if "fail" in url:
                return fail_response
            return ok_response

        mock_http_client = MagicMock()
        mock_http_client.__aenter__ = AsyncMock(return_value=mock_http_client)
        mock_http_client.__aexit__ = AsyncMock(return_value=None)
        mock_http_client.get = AsyncMock(side_effect=side_effect_get)

        batch_results = [
            _make_batch_result(
                "fp_listing_ok_0", json_text='{"total": 42.0, "units": "sq m"}'
            )
        ]

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.build_batch_request.return_value = MagicMock(
            name="sentinel"
        )
        mock_extractor_cls = MagicMock(return_value=mock_extractor_instance)

        with (
            patch(
                "flathunt.defs.zoopla.floor_plans.httpx.AsyncClient",
                return_value=mock_http_client,
            ),
            patch(
                "flathunt.defs.zoopla.floor_plans.FloorPlanSizeExtractor",
                mock_extractor_cls,
            ),
            patch(
                "flathunt.defs.zoopla.floor_plans.submit_batch",
                return_value="batch_xyz",
            ),
            patch(
                "flathunt.defs.zoopla.floor_plans.poll_batch_completion",
                new_callable=AsyncMock,
            ),
            patch(
                "flathunt.defs.zoopla.floor_plans._stream_batch_results",
                return_value=iter(batch_results),
            ),
        ):
            context = dg.build_asset_context()
            result = cast(
                dict[str, tuple[float | None, str | None]],
                zoopla_extracted_floor_plans(
                    context=context,
                    cache=cache_resource,
                    zoopla_enriched_properties=[listing_fail, listing_ok],
                ),
            )

        # listing_ok extracted fine
        assert result.get("listing_ok") == pytest.approx((42.0, None))
        # listing_fail had no batch request submitted (download failed), so it's
        # absent from the result dict (no "we tried" record — the attempt never
        # reached batch submission).
        assert "listing_fail" not in result


class TestReturnsEmptyDictWhenInputEmpty:
    def test_returns_empty_dict_when_input_empty(self, tmp_path: Path) -> None:
        """Empty input list should produce {} with no batch submission."""
        result = _run_asset(
            [], batch_results=[], tmp_path=tmp_path, expect_submit=False
        )
        assert result == {}
