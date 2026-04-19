import asyncio
import logging
import types
from typing import Any

import httpx
from httpx_limiter.abstract_async_limiter import AbstractAsyncLimiter
from httpx_limiter.async_rate_limited_transport import AsyncRateLimitedTransport
from httpx_limiter.rate import Rate
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from tfl import exceptions

logger = logging.getLogger(__name__)

API_BASE_URL = "https://api.tfl.gov.uk"


class _SemaphoreRateLimiter(AbstractAsyncLimiter):
    """Token-bucket rate limiter backed by asyncio.Semaphore.

    Allows at most ``rate.magnitude`` requests per ``rate.duration`` window.
    """

    def __init__(self, rate: Rate) -> None:
        self._semaphore = asyncio.Semaphore(rate.magnitude)
        self._window = rate.in_seconds()

    async def __aenter__(self) -> "_SemaphoreRateLimiter":
        await self._semaphore.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        asyncio.get_event_loop().call_later(self._window, self._semaphore.release)


def get_ratelimited_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=API_BASE_URL,
        transport=AsyncRateLimitedTransport.create(
            _SemaphoreRateLimiter(Rate.create(magnitude=(25 - 1), duration=3))
        ),
        timeout=httpx.Timeout(30.0),
    )


def _is_retryable_error(exception: BaseException) -> bool:
    """Check if exception is an HTTP 5xx server error or 429 rate limit error."""
    if isinstance(
        exception, httpx.TimeoutException | httpx.NetworkError | httpx.ProtocolError
    ):
        return True
    if isinstance(exception, exceptions.JourneyNotFoundError):
        return False
    if isinstance(exception, exceptions.TflApiError):
        status = exception.http_status_code
        return status is not None and (status >= 500 or status == 429)
    if not isinstance(exception, httpx.HTTPStatusError):
        return False
    status_code = exception.response.status_code
    return status_code >= 500 or status_code == 429


def _get_wait_time(retry_state) -> float:
    """Get wait time based on retry-after header or exponential backoff."""
    if retry_state.outcome.exception():
        exception = retry_state.outcome.exception()
        if isinstance(exception, httpx.HTTPStatusError):
            retry_after = exception.response.headers.get("retry-after")
            if retry_after:
                try:
                    return float(retry_after)
                except ValueError:
                    pass
    # Fall back to exponential backoff
    return wait_exponential(multiplier=1, min=1, max=10)(retry_state)


@retry(
    retry=retry_if_exception(_is_retryable_error),
    stop=stop_after_attempt(10),
    wait=_get_wait_time,
    reraise=True,
)
async def get(
    client: httpx.AsyncClient, url: str, parameters: dict[str, Any]
) -> tuple[int, bytes]:
    try:
        response = await client.get(url, params=parameters)
        # Disambigious Results
        if response.status_code == 300:
            return response.status_code, response.content
        response.raise_for_status()
        return response.status_code, response.content
    except httpx.HTTPStatusError as e:
        e.add_note(e.response.text)
        try:
            error_data = e.response.json()
            message = error_data.get(
                "message", e.response.reason_phrase or "HTTP error"
            )
            exception_type = error_data.get("exceptionType")
            http_status_code = (
                error_data.get("httpStatusCode") or e.response.status_code
            )

            if exception_type == "EntityNotFoundException":
                logger.debug(
                    "No journey found (404 EntityNotFoundException) for URL %s: %s",
                    url,
                    message,
                )
                raise exceptions.JourneyNotFoundError(
                    message=message,
                    http_status_code=http_status_code,
                    exception_type=exception_type,
                    timestamp_utc=error_data.get("timestampUtc"),
                    relative_uri=error_data.get("relativeUri"),
                ) from e
            else:
                logger.error(
                    "HTTP error %s for URL %s with headers %s and content %s",
                    e.response.status_code,
                    url,
                    e.response.headers,
                    e.response.content,
                )
                raise exceptions.TflApiError(
                    message=message,
                    http_status_code=http_status_code,
                    exception_type=exception_type,
                    timestamp_utc=error_data.get("timestampUtc"),
                    relative_uri=error_data.get("relativeUri"),
                ) from e
        except (ValueError, KeyError):
            logger.error(
                "HTTP error %s for URL %s with headers %s and content %s",
                e.response.status_code,
                url,
                e.response.headers,
                e.response.content,
            )
            raise exceptions.TflApiError(
                message=str(e),
                http_status_code=e.response.status_code,
            ) from e
