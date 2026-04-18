import asyncio
import hashlib
import json
import os
import time

import dagster as dg

import tfl.api
import tfl.models

roads_shapefile: dg.AssetSpec = dg.AssetSpec(key="roads_shapefile")
tfl_network_topology: dg.AssetSpec = dg.AssetSpec(key="tfl_network_topology")

_TFL_CHECK_INTERVAL = 6 * 3600  # seconds


@dg.sensor(minimum_interval_seconds=900)
def monitor_map_file_and_tfl_lines(
    context: dg.SensorEvaluationContext,
) -> dg.SensorResult:
    cursor = json.loads(context.cursor) if context.cursor else {}
    events = []

    # roads_shapefile: O(1) mtime+size check
    file_path = os.getenv(
        "FLATHUNT_ROADS_FILE_PATH",
        "greater-london-251126-free/gis_osm_roads_free_1.shp",
    )
    stat = os.stat(file_path)
    roads_version = f"{stat.st_mtime_ns}-{stat.st_size}"
    if cursor.get("roads_version") != roads_version:
        context.log.info(f"roads shapefile changed, new version: {roads_version}")
        events.append(
            dg.AssetMaterialization(
                asset_key=roads_shapefile.key,
                tags={"dagster/data_version": roads_version},
                metadata={"file_path": file_path, "size_bytes": int(stat.st_size)},
            )
        )
        cursor["roads_version"] = roads_version

    # tfl_network_topology: lightweight line-list probe, at most every 6 hours
    now = time.time()
    if now - cursor.get("tfl_last_checked", 0) >= _TFL_CHECK_INTERVAL:
        tfl_api_key = os.environ["FLATHUNT__TFL_API_KEY"]
        client = tfl.api.Tfl(app_key=tfl_api_key)
        lines = asyncio.run(client.get_all_lines_routes())
        allowed_modes = {
            tfl.models.ModeId.TUBE,
            tfl.models.ModeId.OVERGROUND,
            tfl.models.ModeId.DLR,
            tfl.models.ModeId.ELIZABETH_LINE,
            tfl.models.ModeId.WALKING,
        }
        tfl_version = hashlib.sha256(
            "|".join(
                sorted(line.id for line in lines if line.mode_name in allowed_modes)
            ).encode()
        ).hexdigest()
        cursor["tfl_last_checked"] = now

        if cursor.get("tfl_version") != tfl_version:
            context.log.info(f"TfL topology changed, new version: {tfl_version}")
            events.append(
                dg.AssetMaterialization(
                    asset_key=tfl_network_topology.key,
                    tags={"dagster/data_version": tfl_version},
                )
            )
            cursor["tfl_version"] = tfl_version

    return dg.SensorResult(
        asset_events=events,
        cursor=json.dumps(cursor),
    )
