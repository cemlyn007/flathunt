import asyncio
import hashlib
import json
import os
import time
from pathlib import Path

import dagster as dg

import tfl.api
import tfl.models

# Asset specifications
roads_shapefile: dg.AssetSpec = dg.AssetSpec(key="roads_shapefile")
tfl_network_topology: dg.AssetSpec = dg.AssetSpec(key="tfl_network_topology")

# Configuration constants
_TFL_CHECK_INTERVAL = 6 * 3600  # seconds
_SENSOR_INTERVAL = 900  # seconds


# Helper functions - private utilities
def _get_roads_file_path() -> str:
    """Get the roads shapefile path from environment or use default."""
    return os.getenv(
        "FLATHUNT_ROADS_FILE_PATH",
        "greater-london-251126-free/gis_osm_roads_free_1.shp",
    )


def _compute_roads_version(file_path: str) -> str:
    """Compute version hash for roads shapefile based on mtime and size."""
    stat = Path(file_path).stat()
    return f"{stat.st_mtime_ns}-{stat.st_size}"


def _check_roads_file(
    context: dg.SensorEvaluationContext,
    cursor: dict,
) -> list[dg.AssetMaterialization]:
    """Check if roads shapefile has changed and return materialization events."""
    events = []
    file_path = _get_roads_file_path()
    roads_version = _compute_roads_version(file_path)

    if cursor.get("roads_version") != roads_version:
        context.log.info("roads shapefile changed, new version: %s", roads_version)
        stat = Path(file_path).stat()
        events.append(
            dg.AssetMaterialization(
                asset_key=roads_shapefile.key,
                tags={"dagster/data_version": roads_version},
                metadata={"file_path": file_path, "size_bytes": int(stat.st_size)},
            )
        )
        cursor["roads_version"] = roads_version

    return events


def _get_allowed_tfl_modes() -> set[tfl.models.ModeId]:
    """Get the set of TfL modes to include in topology checks."""
    return {
        tfl.models.ModeId.TUBE,
        tfl.models.ModeId.OVERGROUND,
        tfl.models.ModeId.DLR,
        tfl.models.ModeId.ELIZABETH_LINE,
        tfl.models.ModeId.WALKING,
    }


def _compute_tfl_version(lines: list[tfl.models.Line]) -> str:
    """Compute version hash for TfL network topology based on active lines."""
    allowed_modes = _get_allowed_tfl_modes()
    return hashlib.sha256(
        "|".join(
            sorted(line.id for line in lines if line.mode_name in allowed_modes)
        ).encode()
    ).hexdigest()


def _check_tfl_topology(
    context: dg.SensorEvaluationContext,
    cursor: dict,
    now: float,
) -> list[dg.AssetMaterialization]:
    """Check if TfL network topology has changed and return materialization events."""
    events = []

    # Lightweight line-list probe, at most every 6 hours
    if now - cursor.get("tfl_last_checked", 0) >= _TFL_CHECK_INTERVAL:
        tfl_api_key = os.environ["FLATHUNT__TFL_API_KEY"]
        client = tfl.api.Tfl(app_key=tfl_api_key)
        lines = asyncio.run(client.get_all_lines_routes())
        tfl_version = _compute_tfl_version(lines)
        cursor["tfl_last_checked"] = now

        if cursor.get("tfl_version") != tfl_version:
            context.log.info("TfL topology changed, new version: %s", tfl_version)
            events.append(
                dg.AssetMaterialization(
                    asset_key=tfl_network_topology.key,
                    tags={"dagster/data_version": tfl_version},
                )
            )
            cursor["tfl_version"] = tfl_version

    return events


# Public API - Dagster sensor
@dg.sensor(
    minimum_interval_seconds=_SENSOR_INTERVAL,
    default_status=dg.DefaultSensorStatus.RUNNING,
)
def monitor_map_file_and_tfl_lines(
    context: dg.SensorEvaluationContext,
) -> dg.SensorResult:
    """Monitor roads shapefile and TfL topology for changes.

    Checks roads shapefile on every run (O(1) operation).
    Checks TfL topology at most every 6 hours to avoid API throttling.
    """
    cursor = json.loads(context.cursor) if context.cursor else {}
    events = []

    # Check roads shapefile
    events.extend(_check_roads_file(context, cursor))

    # Check TfL network topology
    now = time.time()
    events.extend(_check_tfl_topology(context, cursor, now))

    return dg.SensorResult(
        asset_events=events,
        cursor=json.dumps(cursor),
    )
