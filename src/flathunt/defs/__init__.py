from flathunt.defs.candidate_properties import candidate_properties
from flathunt.defs.enriched_properties import enriched_properties
from flathunt.defs.isochrone_intersection import isochrone_intersection
from flathunt.defs.matched_property_ids import matched_property_ids
from flathunt.defs.notified_properties import notified_properties
from flathunt.defs.resources import (
    CacheResource,
    ImapResource,
    QueriesResource,
    SmtpResource,
    TflResource,
)
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
    zoopla_alerts_job,
    zoopla_email_sensor,
    zoopla_property_alerts,
)

all_assets = [
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
    zoopla_property_alerts,
]

all_resources = {
    "tfl_resource": TflResource(),
    "cache": CacheResource(),
    "queries": QueriesResource(),
    "smtp": SmtpResource(),
    "imap": ImapResource(),
}

all_sensors = [
    monitor_roads_shapefile,
    monitor_tfl_topology,
    zoopla_email_sensor,
]

all_jobs = [
    zoopla_alerts_job,
]
