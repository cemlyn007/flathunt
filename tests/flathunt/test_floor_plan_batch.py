"""Tests for the shared Anthropic-batch helpers in flathunt.floor_plan_batch."""

import itertools

import pytest

from flathunt.floor_plan_batch import (
    BATCH_POLL_BACKOFF,
    BATCH_POLL_INITIAL_DELAY,
    BATCH_POLL_MAX_DELAY,
    calculate_backoff_delay,
    extract_json_from_response,
    parse_floor_plan_result,
)


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


class TestParseFloorPlanResult:
    def test_parse_floor_plan_result_with_total(self):
        json_content = '{"total": 65.0, "units": "sq m"}'
        total_sqm, breakdown_csv = parse_floor_plan_result(json_content)
        assert total_sqm == pytest.approx(65.0)
        assert breakdown_csv is None

    def test_parse_floor_plan_result_with_breakdown(self):
        json_content = '{"breakdown": [30, 35], "units": "sq m"}'
        total_sqm, breakdown_csv = parse_floor_plan_result(json_content)
        # get_total_sqm returns max of breakdown when no total
        assert total_sqm == pytest.approx(35.0)
        # get_breakdown_csv returns comma-joined 1-decimal strings
        assert breakdown_csv == "30.0,35.0"

    def test_parse_floor_plan_result_with_null_extraction(self):
        total_sqm, breakdown_csv = parse_floor_plan_result("null")
        assert total_sqm is None
        assert breakdown_csv is None

    def test_parse_floor_plan_result_with_empty_object(self):
        # All fields None -> is_empty() returns True
        total_sqm, breakdown_csv = parse_floor_plan_result("{}")
        assert total_sqm is None
        assert breakdown_csv is None
