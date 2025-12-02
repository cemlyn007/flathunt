import os

import dagster as dg
import networkx as nx
import numpy as np
import tqdm
from pydantic import Field
from shapely.geometry import LineString


class Config(dg.Config):
    file_path: str = Field(
        default_factory=lambda: os.environ.get(
            "FLATHUNT__ROADS_FILE_PATH",
            "greater-london-251126-free/gis_osm_roads_free_1.shp",
        )
    )
    meters_per_minute: float = 60
    station_cost_minutes: float = 5


def euclidean(x1, y1, x2, y2):
    return np.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def find_nearest_node(x1, y1, x2, y2):
    """Find the nearest node to a given (x, y) coordinate."""
    distances = euclidean(x1, y1, x2, y2)
    return distances.argmin(axis=0).item()


@dg.asset
def roads_and_transport(
    context: dg.AssetExecutionContext,
    config: Config,
    roads: nx.Graph,
    transport: nx.Graph,
) -> nx.Graph:
    graph = nx.compose_all([roads, transport])
    non_transport_nodes = list(roads.nodes)
    points = np.array([(data["x"], data["y"]) for _, data in roads.nodes(data=True)])
    for transport_node_key in tqdm.tqdm(transport.nodes):
        x = transport.nodes[transport_node_key]["x"]
        y = transport.nodes[transport_node_key]["y"]
        closest = find_nearest_node(x, y, points[:, 0], points[:, 1])
        non_transport_key = non_transport_nodes[closest]
        length = euclidean(
            x,
            y,
            roads.nodes[non_transport_key]["x"],
            roads.nodes[non_transport_key]["y"],
        ).item()
        duration = length / config.meters_per_minute + config.station_cost_minutes
        graph.add_edge(
            transport_node_key,
            non_transport_key,
            length=length,
            duration=duration,
            geometry=LineString(
                [
                    (x, y),
                    (
                        roads.nodes[non_transport_key]["x"],
                        roads.nodes[non_transport_key]["y"],
                    ),
                ]
            ),
        )
    return graph
