import os
from collections.abc import Iterator

import dagster as dg

from flathunt.defs.candidate_properties import candidate_properties
from flathunt.defs.enriched_properties import enriched_properties
from flathunt.defs.isochrone_intersection import isochrone_intersection
from flathunt.defs.matched_property_ids import matched_property_ids
from flathunt.defs.notified_properties import notified_properties
from flathunt.defs.roads import roads
from flathunt.defs.roads_and_transport import roads_and_transport
from flathunt.defs.sources import (
    monitor_map_file_and_tfl_lines,
    roads_shapefile,
    tfl_network_topology,
)
from flathunt.defs.transport import transport

_DAILY_CRON = os.environ.get("FLATHUNT__DAILY_CRON", "0 22 * * *")

flathunt_job = dg.define_asset_job(
    name="flathunt",
    selection=[
        isochrone_intersection,
        candidate_properties,
        matched_property_ids,
        enriched_properties,
        notified_properties,
    ],
    config=dg.config_from_files(["flathunt_run_config.yaml"]),
)

flathunt_schedule = dg.ScheduleDefinition(
    job=flathunt_job,
    cron_schedule=_DAILY_CRON,
)


@dg.asset_sensor(
    asset_key=dg.AssetKey("roads_and_transport"),
    job=flathunt_job,
    default_status=dg.DefaultSensorStatus.RUNNING,
)
def flathunt_on_graph_update(
    context: dg.SensorEvaluationContext,
    asset_event: dg.EventLogEntry,
) -> Iterator[dg.RunRequest]:
    yield dg.RunRequest(run_key=asset_event.run_id)


defs = dg.Definitions(
    assets=[
        roads_shapefile,
        tfl_network_topology,
        roads,
        transport,
        roads_and_transport,
        isochrone_intersection,
        candidate_properties,
        matched_property_ids,
        enriched_properties,
        notified_properties,
    ],
    jobs=[flathunt_job],
    schedules=[flathunt_schedule],
    sensors=[
        monitor_map_file_and_tfl_lines,
        dg.AutomationConditionSensorDefinition(
            name="flathunt_automation_sensor",
            target=dg.AssetSelection.assets(roads, transport, roads_and_transport),
            default_status=dg.DefaultSensorStatus.RUNNING,
        ),
        flathunt_on_graph_update,
    ],
)
