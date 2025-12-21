import concurrent.futures
import itertools
import pickle
import threading
from collections.abc import Hashable
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import tqdm
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon

NODE_BUFFER = 0
EDGE_BUFFER = 25


def project_to_meters(lon: float, lat: float):
    point_wgs84 = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326")
    point_osgb36 = point_wgs84.to_crs("EPSG:27700")
    return point_osgb36.x.item(), point_osgb36.y.item()


def isochrones(graph: nx.Graph, node: Hashable, trip_time: float) -> list[nx.Graph]:
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


def make_poly(graph: nx.Graph, edge_buff: float, node_buff: float):
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


def euclidean(x1, y1, x2, y2):
    return np.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def find_nearest_node(x1, y1, x2, y2):
    """Find the nearest node to a given (x, y) coordinate."""
    distances = euclidean(x1, y1, x2, y2)
    return distances.argmin(axis=0).item()


def load_graph(station_cost: float) -> nx.Graph:
    graph = pickle.loads(Path(".dagster/storage/roads_and_transport").read_bytes())
    for n_fr, n_to in graph.edges():
        if "station_name" in graph.nodes[n_fr] or "station_name" in graph.nodes[n_to]:
            graph.edges[n_fr, n_to]["duration"] += station_cost
    return graph


def lookup(
    graph: nx.Graph, lon: float, lat: float, max_duration: float
) -> list[nx.Graph]:
    x, y = project_to_meters(lon, lat)
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


def get_graph_bounds(graph: nx.Graph) -> tuple[float, float, float, float]:
    x_coords = [data["x"] for node, data in graph.nodes(data=True)]
    y_coords = [data["y"] for node, data in graph.nodes(data=True)]
    min_x = min(x_coords)
    max_x = max(x_coords)
    min_y = min(y_coords)
    max_y = max(y_coords)
    return min_x, min_y, max_x, max_y


def bounds_to_polygon(bounds: tuple[float, float, float, float]) -> Polygon:
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


def get_intersection(
    graph: nx.Graph,
    groups: list[list[nx.Graph]],
    executor: concurrent.futures.ThreadPoolExecutor | None = None,
) -> list[nx.Graph]:
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
    polygon: Polygon, max_coords=1000, tol=1e-6, max_iter=1000
):
    """
    Find the minimum tolerance that simplifies a polygon to have fewer than max_coords coordinates.
    Uses binary search to find the smallest tolerance that achieves the target.

    Args:
        polygon: A shapely Polygon
        max_coords: Maximum number of coordinates allowed (default 1000)
        tol: Convergence tolerance for binary search (default 1e-6)
        max_iter: Maximum iterations to prevent infinite loops

    Returns:
        Tuple of (simplified_exterior, tolerance_used)
    """
    exterior = polygon.exterior
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
    best_exterior = exterior.simplify(high)
    best_tolerance = high

    for _ in range(max_iter):
        if high - low < tol:
            break

        mid = (low + high) / 2
        simplified = exterior.simplify(mid)
        num_coords = len(list(simplified.coords))

        if num_coords < max_coords:
            # This tolerance works, try to find a smaller one
            best_exterior = simplified
            best_tolerance = mid
            high = mid
        else:
            # Need more simplification (higher tolerance)
            low = mid

    return best_exterior, best_tolerance


def get_isochrone_polys(
    isochrone_subgraphs: list[list[nx.Graph]],
) -> list[list[Polygon]]:
    isochrone_polys = [[None] * len(subgraphs) for subgraphs in isochrone_subgraphs]
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(
                lambda qi, si, sg: (
                    qi,
                    si,
                    make_poly(sg, EDGE_BUFFER, NODE_BUFFER),
                ),
                query_index,
                subgraph_index,
                subgraph,
            )
            for query_index, subgraphs in enumerate(isochrone_subgraphs)
            for subgraph_index, subgraph in enumerate(subgraphs)
        ]
        for future in tqdm.tqdm(
            concurrent.futures.as_completed(futures),
            total=len(futures),
            desc="Generating isochrone polygons",
        ):
            qi, si, poly = future.result()
            isochrone_polys[qi][si] = poly
    if any(
        any(poly is None for poly in subgraph_polys)
        for subgraph_polys in isochrone_polys
    ):
        raise ValueError("Some isochrone polygons were not generated.")
    return isochrone_polys  # pyright: ignore[reportReturnType]
