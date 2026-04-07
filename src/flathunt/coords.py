from typing import NamedTuple


class LatLon(NamedTuple):
    """A WGS84 coordinate in (latitude, longitude) order.

    Used at external API boundaries (TfL journey planner, Rightmove polyline
    encoding) where lat-first is the expected convention.
    """

    lat: float
    lon: float


class CommuteDest(NamedTuple):
    """A commute destination with a maximum acceptable journey time.

    Coordinates follow GeoJSON / Shapely (longitude, latitude) order, matching
    the ``Location`` model and session-state query convention used throughout
    the UI.
    """

    lon: float
    lat: float
    max_duration: float
