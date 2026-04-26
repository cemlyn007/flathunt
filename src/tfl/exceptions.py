class TflApiError(Exception):
    """Base exception for TfL API errors."""

    def __init__(
        self,
        message: str,
        http_status_code: int | None = None,
        exception_type: str | None = None,
        timestamp_utc: str | None = None,
        relative_uri: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.http_status_code = http_status_code
        self.exception_type = exception_type
        self.timestamp_utc = timestamp_utc
        self.relative_uri = relative_uri
        self.retry_after = retry_after


class JourneyNotFoundError(TflApiError):
    """Raised when no journey is found for the given inputs."""

    pass
