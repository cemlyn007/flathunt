import os
from collections.abc import Iterator

import dagster as dg

from flathunt.defs import all_assets, all_jobs, all_resources, all_sensors
from flathunt.defs.network.roads import roads
from flathunt.defs.network.roads_and_transport import roads_and_transport
from flathunt.defs.network.transport import transport

_DAILY_CRON = os.environ.get("FLATHUNT__DAILY_CRON", "0 22 * * *")

flathunt_job = dg.define_asset_job(
    name="flathunt",
    selection=dg.AssetSelection.groups(
        "rightmove_search",
        "rightmove_email",
        "notification",
        "zoopla",
        "network_data",
    ),
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
) -> Iterator[dg.RunRequest | dg.SkipReason]:
    active = context.instance.get_runs(
        filters=dg.RunsFilter(
            job_name="flathunt",
            statuses=[
                dg.DagsterRunStatus.QUEUED,
                dg.DagsterRunStatus.STARTING,
                dg.DagsterRunStatus.STARTED,
            ],
        )
    )
    if active:
        yield dg.SkipReason(
            f"flathunt already has {len(active)} active run(s); skipping."
        )
        return
    yield dg.RunRequest(run_key=asset_event.run_id)


defs = dg.Definitions(
    assets=all_assets,
    resources=all_resources,
    jobs=[flathunt_job, *all_jobs],
    schedules=[flathunt_schedule],
    sensors=[
        *all_sensors,
        dg.AutomationConditionSensorDefinition(
            name="flathunt_automation_sensor",
            target=dg.AssetSelection.assets(roads, transport, roads_and_transport),
            default_status=dg.DefaultSensorStatus.RUNNING,
        ),
        flathunt_on_graph_update,
    ],
)
