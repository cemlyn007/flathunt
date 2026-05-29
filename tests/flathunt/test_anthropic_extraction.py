"""Tests for the shared Anthropic-batch helpers in flathunt.anthropic_extraction."""

import asyncio
import gc
import itertools
import time
import weakref
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import dagster as dg
import pytest

from flathunt.anthropic_extraction import (
    BATCH_POLL_BACKOFF,
    BATCH_POLL_INITIAL_DELAY,
    BATCH_POLL_MAX_DELAY,
    DESCRIPTION_CACHE_TTL,
    FLOOR_PLAN_CACHE_TTL,
    SQFT_TO_SQM,
    ExtractedAttributes,
    ExtractedPropertyInfo,
    ExtractionKind,
    ExtractionRequest,
    FloorPlanExtraction,
    FloorPlanResult,
    ListingExtractionInput,
    RequestMeta,
    _parse_batch_results,
    _stream_batch_results,
    build_description_request,
    build_floor_plan_request,
    calculate_backoff_delay,
    extract_attributes,
    extract_json_from_response,
)
from flathunt.cache import ModelCache


def _fake_result(
    custom_id, result_type="succeeded", json_text='{"total":59.0,"units":"sq m"}'
):
    r = MagicMock()
    r.custom_id = custom_id
    r.result = MagicMock()
    r.result.type = result_type
    if result_type == "succeeded":
        block = MagicMock()
        block.text = json_text
        r.result.message = MagicMock()
        r.result.message.content = [block]
    return r


class TestCalculateBackoffDelay:
    def test_calculate_backoff_delay_starts_at_initial(self):
        assert calculate_backoff_delay(0) == BATCH_POLL_INITIAL_DELAY

    def test_calculate_backoff_delay_grows_then_caps(self):
        delays = [calculate_backoff_delay(i) for i in range(20)]

        # Must be monotonically non-decreasing
        for prev, curr in itertools.pairwise(delays):
            assert curr >= prev

        # Must eventually cap at BATCH_POLL_MAX_DELAY
        assert delays[-1] == BATCH_POLL_MAX_DELAY

        # Must actually grow (not stay flat from the start)
        assert delays[1] > delays[0]

        # Verify the growth factor: delay[1] should be
        # int(INITIAL * BACKOFF^1)
        expected_second = int(BATCH_POLL_INITIAL_DELAY * (BATCH_POLL_BACKOFF**1))
        assert delays[1] == min(expected_second, BATCH_POLL_MAX_DELAY)


class TestExtractJsonFromResponse:
    def test_extract_json_from_response_strips_markdown_fences(self):
        fenced = '```json\n{"key": "value"}\n```'
        assert extract_json_from_response(fenced) == '{"key": "value"}'

    def test_extract_json_from_response_strips_plain_fences(self):
        fenced = '```\n{"key": "value"}\n```'
        assert extract_json_from_response(fenced) == '{"key": "value"}'

    def test_extract_json_from_response_strips_surrounding_whitespace(self):
        padded = '  {"key": "value"}  '
        assert extract_json_from_response(padded) == '{"key": "value"}'

    def test_extract_json_from_response_passes_plain_json_through(self):
        plain = '{"total": 65.0, "units": "sq m"}'
        assert extract_json_from_response(plain) == plain


class TestFloorPlanExtractionModel:
    def test_is_empty_all_none(self):
        e = FloorPlanExtraction(total=None, breakdown=None, units=None)
        assert e.is_empty() is True

    def test_is_empty_false_with_total(self):
        e = FloorPlanExtraction(total=93.0, breakdown=None, units="sq m")
        assert e.is_empty() is False

    def test_is_empty_false_with_breakdown(self):
        e = FloorPlanExtraction(total=None, breakdown=[45.0, 47.0], units="sq m")
        assert e.is_empty() is False

    def test_get_total_sqm_empty(self):
        e = FloorPlanExtraction(total=None, breakdown=None, units=None)
        assert e.get_total_sqm() is None

    def test_get_breakdown_csv_empty(self):
        e = FloorPlanExtraction(total=None, breakdown=None, units=None)
        assert e.get_breakdown_csv() is None

    def test_breakdown_only_sqm_returns_max(self):
        e = FloorPlanExtraction(total=None, breakdown=[45.0, 47.0, 33.0], units="sq m")
        assert e.get_total_sqm() == 47.0
        assert e.get_breakdown_csv() == "45.0,47.0,33.0"

    def test_breakdown_only_sqft_converts_to_sqm(self):
        e = FloorPlanExtraction(total=None, breakdown=[500.0], units="sq ft")
        total_sqm = e.get_total_sqm()
        assert total_sqm is not None and abs(total_sqm - 46.45152) < 0.01

    def test_breakdown_only_no_units_returns_none(self):
        e = FloorPlanExtraction(total=None, breakdown=[45.0, 47.0], units=None)
        assert e.get_total_sqm() is None

    def test_get_total_sqm_sqft(self):
        e = FloorPlanExtraction(total=1000.0, units="sq ft")
        assert e.get_total_sqm() == pytest.approx(1000.0 * SQFT_TO_SQM)


class TestDomainModels:
    def test_floor_plan_result_defaults_to_none(self):
        r = FloorPlanResult()
        assert r.total_sqm is None and r.breakdown_csv is None

    def test_extracted_property_info_has_beds_and_baths(self):
        info = ExtractedPropertyInfo(bedrooms=2, bathrooms=1)
        assert info.bedrooms == 2 and info.bathrooms == 1
        assert info.tenure_type is None
        assert info.years_remaining_on_lease is None

    def test_extracted_attributes_bundles_both(self):
        attrs = ExtractedAttributes(
            floor_plan=FloorPlanResult(total_sqm=59.0),
            description=ExtractedPropertyInfo(council_tax_band="C"),
        )
        assert attrs.floor_plan is not None
        assert attrs.floor_plan.total_sqm == 59.0
        assert attrs.description is not None
        assert attrs.description.council_tax_band == "C"

    def test_extraction_kind_values(self):
        assert ExtractionKind.FLOOR_PLAN == "floor_plan"
        assert ExtractionKind.DESCRIPTION == "description"


class TestRequestBuilders:
    def test_floor_plan_request_has_one_text_and_all_images(self):
        req = build_floor_plan_request(
            "123", [b"\xff\xd8\xff img1", b"\xff\xd8\xff img2"]
        )
        assert isinstance(req, ExtractionRequest)
        assert req.meta.kind == "floor_plan"
        assert req.meta.listing_id == "123"
        assert req.request["custom_id"] == "fp_123"
        params: Any = req.request["params"]
        content: Any = next(iter(params["messages"]))["content"]
        assert content[0]["type"] == "text"
        image_blocks = [c for c in content if c["type"] == "image"]
        assert len(image_blocks) == 2

    def test_description_request_prompt_lists_all_fields(self):
        req = build_description_request(
            "123", "A lovely 2 bed flat, council tax band C."
        )
        assert req.meta.kind == "description"
        assert req.request["custom_id"] == "desc_123"
        params: Any = req.request["params"]
        text: Any = next(iter(params["messages"]))["content"]
        for field in (
            "tenure_type",
            "years_remaining_on_lease",
            "annual_service_charge",
            "annual_ground_rent",
            "council_tax_band",
            "bedrooms",
            "bathrooms",
            "below_ground",
        ):
            assert field in text


class TestParseBatchResults:
    def _parse(self, results, meta):
        with patch(
            "flathunt.anthropic_extraction._stream_batch_results",
            return_value=iter(results),
        ):
            return _parse_batch_results("batch", meta, dg.build_asset_context())

    def test_floor_plan_succeeded_total(self):
        meta = {"fp_1": RequestMeta(kind=ExtractionKind.FLOOR_PLAN, listing_id="1")}
        fp, desc = self._parse([_fake_result("fp_1")], meta)
        assert fp["1"].total_sqm == pytest.approx(59.0)
        assert desc == {}

    def test_floor_plan_empty_is_cached_result(self):
        meta = {"fp_1": RequestMeta(kind=ExtractionKind.FLOOR_PLAN, listing_id="1")}
        fp, _ = self._parse([_fake_result("fp_1", json_text="null")], meta)
        assert "1" in fp and fp["1"].total_sqm is None and fp["1"].breakdown_csv is None
        assert fp["1"].below_ground is None

    def test_errored_produces_no_entry(self):
        meta = {"fp_1": RequestMeta(kind=ExtractionKind.FLOOR_PLAN, listing_id="1")}
        fp, desc = self._parse([_fake_result("fp_1", result_type="errored")], meta)
        assert fp == {} and desc == {}

    def test_description_succeeded(self):
        meta = {"desc_1": RequestMeta(kind=ExtractionKind.DESCRIPTION, listing_id="1")}
        fp, desc = self._parse(
            [_fake_result("desc_1", json_text='{"council_tax_band":"C","bedrooms":2}')],
            meta,
        )
        assert desc["1"].council_tax_band == "C" and desc["1"].bedrooms == 2
        assert fp == {}

    def test_floor_plan_carries_below_ground_with_area(self):
        meta = {"fp_1": RequestMeta(kind=ExtractionKind.FLOOR_PLAN, listing_id="1")}
        fp, _ = self._parse(
            [
                _fake_result(
                    "fp_1",
                    json_text='{"total":59.0,"units":"sq m","below_ground":true}',
                )
            ],
            meta,
        )
        assert fp["1"].total_sqm == pytest.approx(59.0)
        assert fp["1"].below_ground is True

    def test_floor_plan_carries_below_ground_without_area(self):
        meta = {"fp_1": RequestMeta(kind=ExtractionKind.FLOOR_PLAN, listing_id="1")}
        fp, _ = self._parse(
            [_fake_result("fp_1", json_text='{"below_ground":true}')],
            meta,
        )
        assert fp["1"].total_sqm is None
        assert fp["1"].breakdown_csv is None
        assert fp["1"].below_ground is True

    def test_description_carries_below_ground(self):
        meta = {"desc_1": RequestMeta(kind=ExtractionKind.DESCRIPTION, listing_id="1")}
        _, desc = self._parse(
            [_fake_result("desc_1", json_text='{"below_ground":false}')],
            meta,
        )
        assert desc["1"].below_ground is False


def _caches(
    tmp_path: Path,
) -> tuple[ModelCache[FloorPlanResult], ModelCache[ExtractedPropertyInfo]]:
    fp = ModelCache(FloorPlanResult, tmp_path / "fp.db", ttl=FLOOR_PLAN_CACHE_TTL)
    desc = ModelCache(
        ExtractedPropertyInfo, tmp_path / "desc.db", ttl=DESCRIPTION_CACHE_TTL
    )
    return fp, desc


def _run(
    inputs: list[ListingExtractionInput],
    batch_results: list[Any],
    tmp_path: Path,
    *,
    expect_submit: bool = True,
) -> tuple[
    dict[str, ExtractedAttributes],
    ModelCache[FloorPlanResult],
    ModelCache[ExtractedPropertyInfo],
]:
    fp_cache, desc_cache = _caches(tmp_path)
    http_resp = MagicMock()
    http_resp.content = b"\xff\xd8\xff fake"
    http_resp.raise_for_status = MagicMock()
    http_client = MagicMock()
    http_client.__aenter__ = AsyncMock(return_value=http_client)
    http_client.__aexit__ = AsyncMock(return_value=None)
    http_client.get = AsyncMock(return_value=http_resp)
    with (
        patch(
            "flathunt.anthropic_extraction.httpx.AsyncClient", return_value=http_client
        ),
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
            extract_attributes(inputs, fp_cache, desc_cache, dg.build_asset_context())
        )
        if not expect_submit:
            sub.assert_not_called()
        return out, fp_cache, desc_cache


class TestExtractAttributes:
    def test_floor_plan_and_description_both_extracted(self, tmp_path: Path) -> None:
        inputs = [
            ListingExtractionInput(
                listing_id="1",
                description="2 bed flat band C",
                floor_plan_image_urls=["http://x/1.jpg"],
                needs_floor_plan=True,
                needs_description=True,
            )
        ]
        results = [
            _fake_result("fp_1", json_text='{"total":59.0,"units":"sq m"}'),
            _fake_result("desc_1", json_text='{"council_tax_band":"C","bedrooms":2}'),
        ]
        out, fp_cache, desc_cache = _run(inputs, results, tmp_path)
        assert out["1"].floor_plan is not None
        assert out["1"].floor_plan.total_sqm == pytest.approx(59.0)
        assert out["1"].description is not None
        assert out["1"].description.bedrooms == 2
        assert fp_cache.get("1").total_sqm == pytest.approx(59.0)
        assert desc_cache.get("1").council_tax_band == "C"

    def test_cache_hit_skips_submit(self, tmp_path: Path) -> None:
        fp_cache, _ = _caches(tmp_path)
        fp_cache.update([("1", FloorPlanResult(total_sqm=80.0))])
        inputs = [
            ListingExtractionInput(
                listing_id="1",
                description=None,
                floor_plan_image_urls=["http://x/1.jpg"],
                needs_floor_plan=True,
                needs_description=False,
            )
        ]
        out, _, _ = _run(inputs, [], tmp_path, expect_submit=False)
        assert out["1"].floor_plan is not None
        assert out["1"].floor_plan.total_sqm == pytest.approx(80.0)

    def test_no_requests_when_nothing_needed(self, tmp_path: Path) -> None:
        inputs = [
            ListingExtractionInput(
                listing_id="1",
                description=None,
                floor_plan_image_urls=[],
                needs_floor_plan=False,
                needs_description=False,
            )
        ]
        out, _, _ = _run(inputs, [], tmp_path, expect_submit=False)
        assert out["1"].floor_plan is None and out["1"].description is None

    def test_all_image_downloads_fail_means_no_request_no_cache(
        self, tmp_path: Path
    ) -> None:
        fp_cache, desc_cache = _caches(tmp_path)
        http_client = MagicMock()
        http_client.__aenter__ = AsyncMock(return_value=http_client)
        http_client.__aexit__ = AsyncMock(return_value=None)
        http_client.get = AsyncMock(side_effect=Exception("boom"))
        inputs = [
            ListingExtractionInput(
                listing_id="1",
                description=None,
                floor_plan_image_urls=["http://x/1.jpg"],
                needs_floor_plan=True,
                needs_description=False,
            )
        ]
        with (
            patch(
                "flathunt.anthropic_extraction.httpx.AsyncClient",
                return_value=http_client,
            ),
            patch("flathunt.anthropic_extraction.submit_batch") as sub,
            patch(
                "flathunt.anthropic_extraction.poll_batch_completion",
                new_callable=AsyncMock,
            ),
            patch(
                "flathunt.anthropic_extraction._stream_batch_results",
                return_value=iter([]),
            ),
        ):
            out = asyncio.run(
                extract_attributes(
                    inputs, fp_cache, desc_cache, dg.build_asset_context()
                )
            )
            sub.assert_not_called()
        assert out["1"].floor_plan is None
        with pytest.raises(KeyError):
            fp_cache.get("1")


class TestIsBelowGround:
    @pytest.mark.parametrize(
        "fp_signal,desc_signal,expected",
        [
            (True, True, True),
            (True, None, True),
            (None, True, True),
            (False, False, False),
            (False, None, False),
            (None, False, False),
            (None, None, None),
            (True, False, None),
            (False, True, None),
        ],
    )
    def test_reconcile(self, fp_signal, desc_signal, expected):
        attrs = ExtractedAttributes(
            floor_plan=FloorPlanResult(below_ground=fp_signal),
            description=ExtractedPropertyInfo(below_ground=desc_signal),
        )
        assert attrs.is_below_ground() is expected

    def test_reconcile_missing_sources(self):
        assert ExtractedAttributes().is_below_ground() is None

    def test_reconcile_only_floor_plan(self):
        attrs = ExtractedAttributes(floor_plan=FloorPlanResult(below_ground=True))
        assert attrs.is_below_ground() is True

    def test_reconcile_only_description(self):
        attrs = ExtractedAttributes(
            description=ExtractedPropertyInfo(below_ground=False)
        )
        assert attrs.is_below_ground() is False


class TestExtractAttributesCacheSemantics:
    def test_partial_cache_hit_only_fetches_missing_dimension(self, tmp_path):
        # floor plan already cached; description must be fetched.
        fp_cache, _ = _caches(tmp_path)
        fp_cache.update([("1", FloorPlanResult(total_sqm=70.0))])
        inputs = [
            ListingExtractionInput(
                listing_id="1",
                description="band C 2 bed",
                floor_plan_image_urls=["http://x/1.jpg"],
                needs_floor_plan=True,
                needs_description=True,
            )
        ]
        results = [_fake_result("desc_1", json_text='{"council_tax_band":"C"}')]
        out, _, _ = _run(inputs, results, tmp_path)
        assert out["1"].floor_plan is not None
        assert out["1"].floor_plan.total_sqm == pytest.approx(70.0)  # from cache
        assert out["1"].description is not None
        assert out["1"].description.council_tax_band == "C"  # freshly fetched

    def test_expired_cache_entry_is_re_extracted(self, tmp_path):
        # A stale-timestamped floor-plan row (older than TTL) must NOT be served;
        # extract_attributes should re-extract and return the fresh value.
        # We patch _purge_expired so the stale row survives cache construction,
        # and can then only be skipped by a TTL-aware reader (get), not peek.
        with patch("flathunt.cache.ModelCache._purge_expired"):
            fp_cache, _ = _caches(tmp_path)
            stale_item = fp_cache._adapter.dump_json(
                FloorPlanResult(total_sqm=99.0)
            ).decode()
            fp_cache._conn.execute(
                "INSERT OR REPLACE INTO cache (key, timestamp, item) VALUES (?, ?, ?)",
                ("1", time.time() - 10**9, stale_item),
            )
            fp_cache._conn.commit()
            inputs = [
                ListingExtractionInput(
                    listing_id="1",
                    description=None,
                    floor_plan_image_urls=["http://x/1.jpg"],
                    needs_floor_plan=True,
                    needs_description=False,
                )
            ]
            results = [_fake_result("fp_1", json_text='{"total":59.0,"units":"sq m"}')]
            out, _, _ = _run(inputs, results, tmp_path)
        assert out["1"].floor_plan is not None
        assert out["1"].floor_plan.total_sqm == pytest.approx(59.0)  # fresh, not 99.0


class TestStreamBatchResultsKeepsClientAlive:
    """Regression for httpx.ReadError: [Errno 9] Bad file descriptor mid-stream.

    The Anthropic SDK's JSONLDecoder (returned by ``client.messages.batches.results``)
    holds only the ``httpx.Response`` — it does NOT hold a back-reference to the
    ``Anthropic`` client. ``SyncHttpxClientWrapper.__del__`` calls ``self.close()``
    which closes the transport and the underlying socket. So if the function that
    creates the client returns the iterator and lets the ``client`` local fall out
    of scope, the socket gets closed mid-stream and the next read fails with
    ``[Errno 9] Bad file descriptor`` — observed in production for ~7% of batch
    runs after the c644194 refactor.

    The fix is to make ``_stream_batch_results`` a generator (``yield from``)
    so the ``client`` local is captured in the generator's frame and stays alive
    for the entire iteration.
    """

    def test_client_outlives_returned_iterator(self):
        class _StreamingClient:
            """Plain stand-in for anthropic.Anthropic with the call chain we touch.

            Mirrors the SDK's behaviour: ``.results()`` returns a plain iterator
            that does NOT hold a reference back to the client (just like
            JSONLDecoder, which holds only the http_response).
            """

            def __init__(self, items: list[str]) -> None:
                self._items = items
                # Mirror SDK chain: client.messages.batches.results(batch_id).
                self.messages = self
                self.batches = self

            def results(self, batch_id: str) -> Any:
                return iter(self._items)

        client_refs: list[weakref.ref[_StreamingClient]] = []

        def fake_get_client() -> _StreamingClient:
            client = _StreamingClient(items=["r1", "r2", "r3"])
            client_refs.append(weakref.ref(client))
            return client

        with patch(
            "flathunt.anthropic_extraction.get_client",
            side_effect=fake_get_client,
        ):
            iterator = _stream_batch_results("batch_xyz")
            # Start iteration so the generator frame is established and
            # ``get_client()`` actually runs (generators don't execute their
            # body until first ``next()``).
            first = next(iterator)

        assert first == "r1"

        # CPython refcount cleanup is immediate at refcount=0, but be explicit
        # to defend against future cycles and remain portable across runtimes.
        gc.collect()

        if client_refs[0]() is None:
            raise AssertionError(
                "_stream_batch_results released its Anthropic client before "
                "the returned iterator was fully consumed. "
                "SyncHttpxClientWrapper.__del__ would close the underlying "
                "socket, and the next stream read would fail with "
                "httpx.ReadError: [Errno 9] Bad file descriptor. Make "
                "_stream_batch_results a generator (yield from ...) so the "
                "client is held in the generator frame."
            )

        # Sanity: the iterator still produces the remaining items mid-stream.
        assert list(iterator) == ["r2", "r3"]

        # Once the iterator is gone, the client may be GC'd — confirms the
        # test itself isn't accidentally pinning a reference.
        del iterator
        gc.collect()
        assert client_refs[0]() is None
