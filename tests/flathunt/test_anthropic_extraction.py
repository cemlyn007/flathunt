"""Tests for the shared Anthropic-batch helpers in flathunt.anthropic_extraction."""

import itertools
from typing import Any
from unittest.mock import MagicMock, patch

import dagster as dg
import pytest

from flathunt.anthropic_extraction import (
    BATCH_POLL_BACKOFF,
    BATCH_POLL_INITIAL_DELAY,
    BATCH_POLL_MAX_DELAY,
    SQFT_TO_SQM,
    ExtractedAttributes,
    ExtractedPropertyInfo,
    ExtractionKind,
    ExtractionRequest,
    FloorPlanExtraction,
    FloorPlanResult,
    RequestMeta,
    _parse_batch_results,
    build_description_request,
    build_floor_plan_request,
    calculate_backoff_delay,
    extract_json_from_response,
)


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

    def test_floor_plan_extraction_get_total_sqm_sqft(self):
        e = FloorPlanExtraction(total=1000.0, units="sq ft")
        assert e.get_total_sqm() == pytest.approx(1000.0 * SQFT_TO_SQM)


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

    def test_description_request_prompt_lists_all_seven_fields(self):
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
