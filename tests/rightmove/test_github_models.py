import httpx
import pytest

from rightmove._github_models import raise_for_status_with_response_details


def test_raise_for_status_with_response_details_adds_retry_after_and_body() -> None:
    request = httpx.Request(
        "POST", "https://models.inference.ai.azure.com/chat/completions"
    )
    response = httpx.Response(
        429,
        request=request,
        headers={"retry-after": "30"},
        text='{"error":{"code":"TooManyRequests","message":"Back off"}}',
    )

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        raise_for_status_with_response_details(response)

    assert exc_info.value.__notes__ == [
        "Retry-After: 30",
        'Response body: {"error":{"code":"TooManyRequests","message":"Back off"}}',
    ]


def test_raise_for_status_with_response_details_notes_empty_body() -> None:
    request = httpx.Request(
        "POST", "https://models.inference.ai.azure.com/chat/completions"
    )
    response = httpx.Response(503, request=request, text="  ")

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        raise_for_status_with_response_details(response)

    assert exc_info.value.__notes__ == ["Response body: <empty>"]
