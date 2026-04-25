import dagster as dg
import networkx as nx
import numpy as np
import tqdm
from shapely.geometry import LineString

from flathunt.geometry import euclidean, find_nearest_node


class Config(dg.Config):
    meters_per_minute: float = 60


def _connect_transport_to_roads(
    graph: nx.Graph,
    roads: nx.Graph,
    transport: nx.Graph,
    meters_per_minute: float,
) -> nx.Graph:
    """Connect transport nodes to the nearest road nodes.

    Args:
        graph: The combined graph to modify.
        roads: The roads graph containing road nodes.
        transport: The transport graph containing station nodes.
        meters_per_minute: Conversion factor for computing edge durations.

    Returns:
        The modified graph with transport-to-roads connections.
    """
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
        duration = length / meters_per_minute
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


@dg.asset(
    automation_condition=dg.AutomationCondition.eager(), group_name="network_data"
)
def roads_and_transport(
    config: Config,
    roads: nx.Graph,
    transport: nx.Graph,
) -> nx.Graph:
    """Merge road and transport graphs, connecting transport nodes to nearby road nodes.

    Creates a unified transportation network by composing the road and transport
    graphs, then adding edges from each transport (station) node to its nearest
    road node to enable transfers between the two networks.

    Args:
        config: Asset configuration with meters_per_minute conversion factor.
        roads: NetworkX graph of road network.
        transport: NetworkX graph of public transit network.

    Returns:
        A merged NetworkX graph with both road and transport connectivity.
    """
    graph = nx.compose_all([roads, transport])
    graph = _connect_transport_to_roads(
        graph, roads, transport, config.meters_per_minute
    )
    return graph
