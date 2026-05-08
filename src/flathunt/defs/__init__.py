from pathlib import Path

import dagster as dg
import yaml

from flathunt.defs.network import (
    isochrone_intersection,
    monitor_roads_shapefile,
    monitor_tfl_topology,
    roads,
    roads_and_transport,
    roads_shapefile,
    tfl_network_topology,
    transport,
)
from flathunt.defs.paths import REPO_ROOT
from flathunt.defs.resources import (
    CacheResource,
    ImapResource,
    QueriesResource,
    SmtpResource,
    TflResource,
)
from flathunt.defs.rightmove_email import (
    rightmove_email_matched_properties,
    rightmove_email_sensor,
    rightmove_enriched_properties,
    rightmove_notified_properties,
    rightmove_property_alerts,
)
from flathunt.defs.rightmove_search import (
    candidate_properties,
    enriched_properties,
    matched_property_ids,
    notified_properties,
    rightmove_property_details,
)
from flathunt.defs.zoopla import (
    zoopla_email_sensor,
    zoopla_enriched_properties,
    zoopla_extracted_floor_plans,
    zoopla_matched_properties,
    zoopla_notified_properties,
    zoopla_property_alerts,
)

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
    zoopla_extracted_floor_plans,
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
        "zoopla_extracted_floor_plans",
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
