import httpx

_MAX_ERROR_BODY_CHARS = 4_000


def raise_for_status_with_response_details(response: httpx.Response) -> None:
    """Raise HTTP errors with response details attached for downstream logging."""
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        retry_after = response.headers.get("retry-after")
        if retry_after:
            exc.add_note(f"Retry-After: {retry_after}")

        body = response.text.strip()
        if body:
            if len(body) > _MAX_ERROR_BODY_CHARS:
                body = f"{body[:_MAX_ERROR_BODY_CHARS]}..."
            exc.add_note(f"Response body: {body}")
        else:
            exc.add_note("Response body: <empty>")
        raise
