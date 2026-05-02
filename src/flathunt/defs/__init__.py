from pathlib import Path

import dagster as dg
import yaml

from flathunt.defs.candidate_properties import candidate_properties
from flathunt.defs.enriched_properties import enriched_properties
from flathunt.defs.isochrone_intersection import isochrone_intersection
from flathunt.defs.matched_property_ids import matched_property_ids
from flathunt.defs.notified_properties import notified_properties
from flathunt.defs.paths import REPO_ROOT
from flathunt.defs.resources import (
    CacheResource,
    ImapResource,
    QueriesResource,
    SmtpResource,
    TflResource,
)
from flathunt.defs.rightmove_alerts import (
    rightmove_email_sensor,
    rightmove_property_alerts,
)
from flathunt.defs.rightmove_email_matched_properties import (
    rightmove_email_matched_properties,
)
from flathunt.defs.rightmove_enriched_properties import rightmove_enriched_properties
from flathunt.defs.rightmove_notified_properties import rightmove_notified_properties
from flathunt.defs.rightmove_property_details import rightmove_property_details
from flathunt.defs.roads import roads
from flathunt.defs.roads_and_transport import roads_and_transport
from flathunt.defs.sources import (
    monitor_roads_shapefile,
    monitor_tfl_topology,
    roads_shapefile,
    tfl_network_topology,
)
from flathunt.defs.transport import transport
from flathunt.defs.zoopla_alerts import (
    zoopla_email_sensor,
    zoopla_property_alerts,
)
from flathunt.defs.zoopla_enriched_properties import zoopla_enriched_properties
from flathunt.defs.zoopla_matched_properties import zoopla_matched_properties
from flathunt.defs.zoopla_notified_properties import zoopla_notified_properties

_resources_cfg = yaml.safe_load((REPO_ROOT / "resources.yaml").read_text())

all_assets = [
    roads_shapefile,
    tfl_network_topology,
    roads,
    transport,
    roads_and_transport,
    isochrone_intersection,
    candidate_properties,
    matched_property_ids,
    rightmove_property_details,
    enriched_properties,
    notified_properties,
    zoopla_property_alerts,
    zoopla_enriched_properties,
    zoopla_matched_properties,
    zoopla_notified_properties,
    rightmove_property_alerts,
    rightmove_enriched_properties,
    rightmove_email_matched_properties,
    rightmove_notified_properties,
]

all_resources = {
    "tfl_resource": TflResource(),
    "cache": CacheResource(**_resources_cfg["cache"]),
    "queries": QueriesResource(**_resources_cfg["queries"]),
    "smtp": SmtpResource(**_resources_cfg["smtp"]),
    "imap": ImapResource(),
    "fs_io_manager": dg.FilesystemIOManager(
        base_dir=str(Path(_resources_cfg["cache"]["data_dir"]) / "dagster_io")
    ),
}

all_sensors = [
    monitor_roads_shapefile,
    monitor_tfl_topology,
    zoopla_email_sensor,
    rightmove_email_sensor,
]

zoopla_job = dg.define_asset_job(
    name="zoopla",
    selection=dg.AssetSelection.assets(
        "zoopla_property_alerts",
        "zoopla_enriched_properties",
        "zoopla_matched_properties",
        "zoopla_notified_properties",
    ),
    config=dg.config_from_files([str(REPO_ROOT / "zoopla_run_config.yaml")]),
)

rightmove_email_job = dg.define_asset_job(
    name="rightmove_email",
    selection=dg.AssetSelection.assets(
        "rightmove_property_alerts",
        "rightmove_enriched_properties",
        "rightmove_email_matched_properties",
        "rightmove_notified_properties",
    ),
    config=dg.config_from_files([str(REPO_ROOT / "rightmove_run_config.yaml")]),
)

rightmove_search_job = dg.define_asset_job(
    name="rightmove_search",
    selection=dg.AssetSelection.assets(
        "candidate_properties",
        "matched_property_ids",
        "rightmove_property_details",
        "enriched_properties",
        "notified_properties",
    ),
    config=dg.config_from_files([str(REPO_ROOT / "rightmove_search_run_config.yaml")]),
)

all_jobs = [zoopla_job, rightmove_email_job, rightmove_search_job]
