from dagster import (
    AssetSelection,
    AutomationConditionSensorDefinition,
    DefaultSensorStatus,
    Definitions,
    config_from_files,
    define_asset_job,
)

from flathunt.defs.candidate_properties import candidate_properties
from flathunt.defs.enriched_properties import enriched_properties
from flathunt.defs.isochrone_intersection import isochrone_intersection
from flathunt.defs.matched_property_ids import matched_property_ids
from flathunt.defs.roads import roads
from flathunt.defs.roads_and_transport import roads_and_transport
from flathunt.defs.sources import (
    monitor_map_file_and_tfl_lines,
    roads_shapefile,
    tfl_network_topology,
)
from flathunt.defs.transport import transport

flathunt_job = define_asset_job(
    name="flathunt",
    selection=[
        isochrone_intersection,
        candidate_properties,
        matched_property_ids,
        enriched_properties,
    ],
    config=config_from_files(["flathunt_run_config.yaml"]),
)

defs = Definitions(
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
    ],
    jobs=[flathunt_job],
    sensors=[
        monitor_map_file_and_tfl_lines,
        AutomationConditionSensorDefinition(
            name="flathunt_automation_sensor",
            target=AssetSelection.all(),
            default_status=DefaultSensorStatus.RUNNING,
        ),
    ],
)
