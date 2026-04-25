"""Coordinate types for different contexts in the application.

This module defines coordinate representations for different use cases:
- LatLon: External API boundaries (lat-first convention)
- CommuteDest: Internal application state (lon-first convention per GeoJSON/Shapely)

The different ordering conventions reflect the expectations of the respective
systems and should be converted at API boundaries as needed.
"""

from typing import NamedTuple

# External API Coordinates
# =======================
# Used at system boundaries where external APIs expect specific coordinate orders.


class LatLon(NamedTuple):
    """A WGS84 coordinate in (latitude, longitude) order.

    Used at external API boundaries (TfL journey planner, Rightmove polyline
    encoding) where lat-first is the expected convention.
    """

    lat: float
    lon: float


# Internal Application Coordinates
# ================================
# Used within the application, following GeoJSON/Shapely conventions.


class CommuteDest(NamedTuple):
    """A commute destination with a maximum acceptable journey time.

    Coordinates follow GeoJSON / Shapely (longitude, latitude) order, matching
    the ``Location`` model and session-state query convention used throughout
    the UI.
    """

    lon: float
    lat: float
    max_duration: float
