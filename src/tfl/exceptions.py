from typing import Optional


class TflApiError(Exception):
    """Base exception for TfL API errors."""

    def __init__(
        self,
        message: str,
        http_status_code: Optional[int] = None,
        exception_type: Optional[str] = None,
        timestamp_utc: Optional[str] = None,
        relative_uri: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.http_status_code = http_status_code
        self.exception_type = exception_type
        self.timestamp_utc = timestamp_utc
        self.relative_uri = relative_uri


class JourneyNotFoundError(TflApiError):
    """Raised when no journey is found for the given inputs."""

    pass
