"""Shared configuration classes for Dagster assets.

This module defines reusable configuration dataclasses used across the
flathunt asset pipeline.
"""

import dagster as dg

# Configuration Classes
# =====================


class CommuteDestConfig(dg.Config):
    """Configuration for a single commute destination.

    Defines a geographic point and the maximum travel duration to that point,
    used for isochrone-based filtering in property searches.

    Attributes:
        lon: Longitude in EPSG:4326 (WGS84) coordinate system.
        lat: Latitude in EPSG:4326 (WGS84) coordinate system.
        max_duration: Maximum acceptable travel duration in minutes.
    """

    lon: float
    lat: float
    max_duration: float
