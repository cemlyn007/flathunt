import concurrent.futures
import itertools
import pickle
import threading
from collections.abc import Hashable
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
from shapely.geometry import Point
from shapely.geometry.polygon import LinearRing, Polygon

from flathunt.geometry import euclidean, wgs84_to_bng

NODE_BUFFER = 0
EDGE_BUFFER = 25


# Simple utility functions
def find_nearest_node(x1, y1, x2, y2):
    """Return the index of the nearest point in an array to a query point.

    Args:
        x1: X coordinate of the query point.
        y1: Y coordinate of the query point.
        x2: NumPy array of X coordinates of candidate points.
        y2: NumPy array of Y coordinates of candidate points.

    Returns:
        Integer index into ``x2``/``y2`` of the closest candidate.
    """
    distances = euclidean(x1, y1, x2, y2)
    return distances.argmin(axis=0).item()


def get_graph_bounds(graph: nx.Graph) -> tuple[float, float, float, float]:
    """Return the axis-aligned bounding box of all nodes in a graph.

    Args:
        graph: A NetworkX graph whose nodes carry ``x`` and ``y`` attributes.

    Returns:
        A tuple ``(min_x, min_y, max_x, max_y)`` in the graph's coordinate system.
    """
    x_coords = [data["x"] for node, data in graph.nodes(data=True)]
    y_coords = [data["y"] for node, data in graph.nodes(data=True)]
    min_x = min(x_coords)
    max_x = max(x_coords)
    min_y = min(y_coords)
    max_y = max(y_coords)
    return min_x, min_y, max_x, max_y


def bounds_to_polygon(bounds: tuple[float, float, float, float]) -> Polygon:
    """Convert an axis-aligned bounding box to a closed rectangular Polygon.

    Args:
        bounds: A ``(min_x, min_y, max_x, max_y)`` tuple.

    Returns:
        A Shapely Polygon representing the bounding rectangle.
    """
    min_x, min_y, max_x, max_y = bounds
    return Polygon(
        [
            (min_x, min_y),
            (min_x, max_y),
            (max_x, max_y),
            (max_x, min_y),
            (min_x, min_y),
        ]
    )


# Core graph loading and isochrone functions
def load_graph(station_cost: float) -> nx.Graph:
    """Load the roads-and-transport graph from Dagster storage and apply a station penalty.

    Args:
        station_cost: Additional duration in minutes added to every edge that
            connects to at least one station node.

    Returns:
        The combined roads-and-transport NetworkX graph with adjusted edge durations.
    """
    graph = pickle.loads(Path(".dagster/storage/roads_and_transport").read_bytes())
    for n_fr, n_to in graph.edges():
        if "station_name" in graph.nodes[n_fr] or "station_name" in graph.nodes[n_to]:
            graph.edges[n_fr, n_to]["duration"] += station_cost
    return graph


def isochrones(graph: nx.Graph, node: Hashable, trip_time: float) -> list[nx.Graph]:
    """Compute reachable subgraphs from a node within a given travel time.

    Transit-only edges (both endpoints have a ``station_name`` attribute) are
    removed before splitting into connected components, so each returned
    subgraph represents a contiguous road-reachable region.

    Args:
        graph: The combined roads-and-transport graph.
        node: The starting node identifier.
        trip_time: Maximum travel duration in minutes.

    Returns:
        A list of subgraphs, one per connected component reachable within
        ``trip_time`` minutes.
    """
    subgraph = nx.ego_graph(graph, node, radius=trip_time, distance="duration")

    remove_edges = set()
    for n_fr, n_to in subgraph.edges():
        if (
            "station_name" in subgraph.nodes[n_fr]
            and "station_name" in subgraph.nodes[n_to]
        ):
            remove_edges.add((n_fr, n_to))

    for n_fr, n_to in remove_edges:
        subgraph.remove_edge(n_fr, n_to)

    subgraphs_nodes = nx.connected_components(subgraph)

    return [nx.subgraph(subgraph, nodes) for nodes in subgraphs_nodes]


def lookup(
    graph: nx.Graph, lon: float, lat: float, max_duration: float
) -> list[nx.Graph]:
    """Find isochrone subgraphs reachable from a WGS84 coordinate within a time limit.

    Args:
        graph: The combined roads-and-transport graph.
        lon: Longitude of the origin point in WGS84.
        lat: Latitude of the origin point in WGS84.
        max_duration: Maximum travel duration in minutes.

    Returns:
        A list of connected subgraphs reachable within ``max_duration`` minutes
        from the road node nearest to the given coordinate.
    """
    x, y = wgs84_to_bng(lon, lat)
    road_nodes = [
        node_id
        for node_id, data in graph.nodes(data=True)
        if "station_name" not in data
    ]
    points = np.array(
        [(graph.nodes[node]["x"], graph.nodes[node]["y"]) for node in road_nodes]
    )
    closest_node_index = find_nearest_node(x, y, points[:, 0], points[:, 1])
    locked_query = road_nodes[closest_node_index]
    subgraphs = isochrones(graph, locked_query, max_duration)
    return subgraphs


def make_poly(graph: nx.Graph, edge_buff: float, node_buff: float):
    """Build a single unioned polygon covering all road nodes and edges in a graph.

    Station-to-station edges are excluded so that transit corridors do not
    inflate the walking polygon.

    Args:
        graph: A subgraph whose nodes carry ``x`` and ``y`` attributes (BNG metres).
        edge_buff: Buffer distance in metres applied to each edge geometry.
        node_buff: Buffer distance in metres applied to each node point.

    Returns:
        A Shapely geometry (typically a Polygon or MultiPolygon) representing
        the union of all buffered nodes and edges.
    """
    node_points = [
        Point((data["x"], data["y"])) for node, data in graph.nodes(data=True)
    ]
    nodes_gdf = gpd.GeoDataFrame({"id": list(graph.nodes)}, geometry=node_points)
    nodes_gdf = nodes_gdf.set_index("id")
    edge_lines = []
    for n_fr, n_to in graph.edges():
        if "station_name" in graph.nodes[n_fr] and "station_name" in graph.nodes[n_to]:
            continue
        edge_lookup = graph.get_edge_data(n_fr, n_to)["geometry"]
        edge_lines.append(edge_lookup)
    n = nodes_gdf.buffer(node_buff).geometry
    e = gpd.GeoSeries(edge_lines).buffer(edge_buff).geometry
    all_gs = list(n) + list(e)
    new_iso = gpd.GeoSeries(all_gs).union_all()
    return new_iso


# Complex algorithms for graph operations
def get_intersection(
    graph: nx.Graph,
    groups: list[list[nx.Graph]],
    executor: concurrent.futures.ThreadPoolExecutor | None = None,
) -> list[nx.Graph]:
    """Compute the pairwise graph intersection across multiple groups of isochrone subgraphs.

    For a single group the subgraphs are returned unchanged. For two groups,
    every pair of subgraphs is intersected and the results are merged back into
    the original graph so that full node/edge attributes are preserved. For more
    than two groups the computation is applied recursively.

    Args:
        graph: The original full graph used to restore node and edge attributes
            after intersection.
        groups: A list of isochrone groups, where each group is a list of
            subgraphs for one query location.
        executor: Optional thread pool to reuse across recursive calls. A new
            pool is created automatically when ``None``.

    Returns:
        A list of connected subgraphs representing the intersection of all groups.
    """
    if executor is None:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            return get_intersection(graph, groups, executor)
    elif len(groups) == 1:
        return groups[0]
    elif len(groups) == 2:
        (a_subgraphs, b_subgraphs) = groups
        a_bound_futures = [
            executor.submit(
                lambda subgraph: bounds_to_polygon(get_graph_bounds(subgraph)), subgraph
            )
            for subgraph in a_subgraphs
        ]
        b_bounds_futures = [
            executor.submit(
                lambda subgraph: bounds_to_polygon(get_graph_bounds(subgraph)), subgraph
            )
            for subgraph in b_subgraphs
        ]
        a_bounds = [future.result() for future in a_bound_futures]
        b_bounds = [future.result() for future in b_bounds_futures]

        lock = threading.Lock()

        def work(a, b, a_bound, b_bound):
            if not a_bound.intersects(b_bound):
                return []
            with lock:
                # Unfortunately this is not thread-safe.
                intersection = nx.intersection(a, b)
            if intersection.number_of_nodes() > 0:
                subgraphs = [
                    nx.subgraph(intersection, nodes)
                    for nodes in nx.connected_components(intersection)
                ]
                compatible_intersections = [g.copy() for g in subgraphs]
                for intersection in compatible_intersections:
                    for node_id, node_attributes in intersection.nodes.items():
                        node_attributes.update(graph.nodes[node_id])
                        for neighbor, edge_attributes in graph[node_id].items():
                            if neighbor in intersection.nodes:
                                intersection.add_edge(
                                    node_id, neighbor, **edge_attributes
                                )
                return compatible_intersections
            return []

        return list(
            itertools.chain.from_iterable(
                executor.map(
                    lambda p: work(p[0][0], p[1][0], p[0][1], p[1][1]),
                    itertools.product(
                        zip(a_subgraphs, a_bounds, strict=True),
                        zip(b_subgraphs, b_bounds, strict=True),
                    ),
                )
            )
        )
    else:
        group, *rest = groups
        subgraphs = get_intersection(graph, rest, executor=executor)
        return get_intersection(graph, [group, subgraphs], executor=executor)


def find_min_simplify_tolerance(
    exterior: LinearRing,
    max_coords: int = 1000,
    tol: float = 1e-6,
    max_iter: int = 1000,
) -> tuple[LinearRing, float]:
    """Find the smallest simplification tolerance that reduces a ring below a coordinate limit.

    Uses binary search to find the minimum Douglas-Peucker tolerance that
    brings the ring below ``max_coords`` vertices.

    Args:
        exterior: The Shapely LinearRing to simplify.
        max_coords: Maximum number of coordinates allowed. Defaults to 1000.
        tol: Convergence threshold for the binary search. Defaults to 1e-6.
        max_iter: Maximum number of binary-search iterations. Defaults to 1000.

    Returns:
        A tuple of ``(simplified_exterior, tolerance_used)``. If the ring is
        already under the limit, ``tolerance_used`` is ``0.0``.

    Raises:
        ValueError: If no tolerance up to 1e6 achieves the coordinate limit.
    """
    original_coords = len(list(exterior.coords))

    # If already under the limit, no simplification needed
    if original_coords < max_coords:
        return exterior, 0.0

    # Find an upper bound that definitely works
    # Start with a reasonable guess and double until we get under max_coords
    high = 1.0
    while len(list(exterior.simplify(high).coords)) >= max_coords:
        high *= 2
        if high > 1e6:  # Safety limit
            raise ValueError(f"Could not simplify polygon below {max_coords} coords")

    # Binary search for minimum tolerance
    low = 0.0
    _simplified = exterior.simplify(high)
    if not isinstance(_simplified, LinearRing):
        raise TypeError(
            f"Expected LinearRing after simplification, got {type(_simplified).__name__}"
        )
    best_exterior = _simplified
    best_tolerance = high

    for _ in range(max_iter):
        if high - low < tol:
            break

        mid = (low + high) / 2
        simplified = exterior.simplify(mid)
        num_coords = len(list(simplified.coords))

        if num_coords < max_coords:
            # This tolerance works, try to find a smaller one
            if not isinstance(simplified, LinearRing):
                raise TypeError(
                    f"Expected LinearRing after simplification, got {type(simplified).__name__}"
                )
            best_exterior = simplified
            best_tolerance = mid
            high = mid
        else:
            # Need more simplification (higher tolerance)
            low = mid

    return best_exterior, best_tolerance
