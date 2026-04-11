import dagster as dg


class CommuteDestConfig(dg.Config):
    """Configuration for a single commute destination."""

    lon: float
    lat: float
    max_duration: float
