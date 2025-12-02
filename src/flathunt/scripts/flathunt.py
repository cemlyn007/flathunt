import concurrent.futures
import multiprocessing.context
import pickle
from collections.abc import Hashable
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
import tqdm
from shapely.geometry import Point

# 0 or 1 disables multiprocessing.
MAX_WORKERS = 0
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


def multi_lookup(
    graph: nx.Graph, queries: list[tuple[float, float, float]]
) -> list[list[nx.Graph]]:
    if MAX_WORKERS in (0, 1):
        results = []
        for longitude_value, latitude_value, max_duration in queries:
            result = lookup(graph, longitude_value, latitude_value, max_duration)
            results.append(result)
        return results
    else:
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=MAX_WORKERS,
            mp_context=multiprocessing.context.ForkServerContext(),
        ) as executor:
            futures = []
            for longitude_value, latitude_value, max_duration in queries:
                future = executor.submit(
                    lookup, graph, longitude_value, latitude_value, max_duration
                )
                futures.append(future)
            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]
    return results


def get_intersection(graph: nx.Graph, groups: list[tuple[list[nx.Graph], list]]):
    if len(groups) == 1:
        subgraphs, polys = groups[0]
        return polys, subgraphs
    if len(groups) == 2:
        pairs = []
        (a_subgraphs, a_polys), (b_subgraphs, b_polys) = groups
        for a_subgraph, a_poly in tqdm.tqdm(
            zip(a_subgraphs, a_polys, strict=True), total=len(a_subgraphs)
        ):
            for b_subgraph, b_poly in zip(b_subgraphs, b_polys, strict=True):
                a_boundary = a_poly.boundary
                b_boundary = b_poly.boundary
                if (
                    a_boundary is not None
                    and b_boundary is not None
                    and a_boundary.intersects(b_boundary)
                ):
                    pairs.append((a_subgraph, b_subgraph))
        compatible_intersections = []
        with tqdm.tqdm(total=len(pairs)) as pbar:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                for intersection in executor.map(
                    nx.intersection, [a for a, b in pairs], [b for a, b in pairs]
                ):
                    if intersection.number_of_nodes() > 0:
                        intersection_subgraphs = list(
                            nx.connected_components(intersection)
                        )
                        compatible_intersections.extend(
                            [
                                nx.subgraph(intersection, nodes)
                                for nodes in intersection_subgraphs
                            ]
                        )
                    pbar.update(1)
        compatible_intersections = [g.copy() for g in compatible_intersections]
        for intersection in compatible_intersections:
            for node_id, node_attributes in intersection.nodes.items():
                # TODO: Why is this happening??
                node_attributes.update(graph.nodes[node_id])
                # Add back the edges
                for neighbor, edge_attributes in graph[node_id].items():
                    if neighbor in intersection.nodes:
                        intersection.add_edge(node_id, neighbor, **edge_attributes)
        all_polys = []
        all_graphs = [compatible_intersections]
        with tqdm.tqdm(total=sum(map(len, all_graphs))) as pbar:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                maps = [
                    executor.map(
                        lambda sg: make_poly(sg, EDGE_BUFFER, NODE_BUFFER), subgraphs
                    )
                    for subgraphs in all_graphs
                ]
                for _map in maps:
                    subgraph_polys = []
                    for subgraph in _map:
                        subgraph_polys.append(subgraph)
                        pbar.update(1)
                    all_polys.append(subgraph_polys)
        (polys,) = all_polys
        return polys, compatible_intersections
    else:
        group, *rest = groups
        polys, subgraphs = get_intersection(graph, rest)
        return get_intersection(graph, [group, (subgraphs, polys)])


if __name__ == "__main__":
    st.header("Flathunt!")
    longitude_value = st.text_input("Enter longitude:", key="longitude_input")
    latitude_value = st.text_input("Enter latitude:", key="latitude_input")
    max_duration = st.slider(
        "Maximum duration (in minutes):", min_value=1, max_value=120, value=30
    )
    add_query = st.button("Add query", key="add_query_button")
    if add_query:
        if not longitude_value or not latitude_value:
            st.status("Please enter both longitude and latitude values.", state="error")
        else:
            try:
                longitude_value = float(longitude_value)
                latitude_value = float(latitude_value)
            except ValueError:
                st.error(
                    "Please enter valid numeric values for longitude and latitude."
                )
                raise ValueError("Invalid input for longitude or latitude.")
            else:
                query = (longitude_value, latitude_value, max_duration)
                queries = st.session_state.get("queries", [])
                if any(
                    (longitude_value, latitude_value)
                    == (other_longitude, other_latitude)
                    for other_longitude, other_latitude, *_ in queries
                ):
                    query_index = next(
                        i
                        for i, (other_longitude, other_latitude, *_) in enumerate(
                            queries
                        )
                        if (longitude_value, latitude_value)
                        == (other_longitude, other_latitude)
                    )
                    queries[query_index] = query
                    st.session_state["processed_queries"] = False
                else:
                    queries.append(query)
                    st.session_state["processed_queries"] = False
                if queries:
                    st.session_state["queries"] = queries
                elif "queries" in st.session_state:
                    del st.session_state["queries"]
                st.status(f"Accepted query: {query}", state="complete")

    if "queries" in st.session_state:
        st.table(
            pd.DataFrame(
                st.session_state["queries"],
                columns=["Longitude", "Latitude", "Max Duration"],
            )
        )
        st.button("Clear queries", on_click=lambda: st.session_state.pop("queries"))

    process = st.button("Process queries", key="process_queries_button")
    if process and (queries := st.session_state.get("queries", [])):
        with st.spinner("Processing..."):
            graph = pickle.loads(
                Path(".dagster/storage/roads_and_transport").read_bytes()
            )
            isochrone_subgraphs = multi_lookup(graph, queries)
            groups = []
            for subgraphs in isochrone_subgraphs:
                polys = []
                for subgraph in subgraphs:
                    poly = make_poly(subgraph, EDGE_BUFFER, NODE_BUFFER)
                    polys.append(poly)
                groups.append((subgraphs, polys))
            polys, intersection_graphs = get_intersection(graph, groups)
        st.status("Completed processing query.", state="complete")
        # Make map

        if len(queries) == 1:
            other_polys = []
        else:
            other_polys = [
                [
                    make_poly(subgraph, EDGE_BUFFER, NODE_BUFFER)
                    for subgraph in subgraphs
                ]
                for subgraphs in isochrone_subgraphs
            ]
        polys = [poly for poly in polys if not poly.is_empty]
        st.write(f"Found {len(polys)} intersection graphs.")

        # Build GeoDataFrame for intersection polygons
        intersection_gdf = gpd.GeoDataFrame(
            {"id": list(range(len(polys))), "type": ["Intersection"] * len(polys)},
            geometry=polys,
            crs="EPSG:27700",
        )

        # Build GeoDataFrame for isochrone polygons (flattened)
        isochrone_polys = []
        isochrone_ids = []
        isochrone_types = []
        for i, poly_list in enumerate(other_polys):
            for poly in poly_list:
                if not poly.is_empty:
                    isochrone_polys.append(poly)
                    isochrone_ids.append(f"isochrone_{i}")
                    isochrone_types.append(f"Query {i}")

        isochrone_gdf = gpd.GeoDataFrame(
            {"id": isochrone_ids, "type": isochrone_types},
            geometry=isochrone_polys,
            crs="EPSG:27700",
        )

        # Combine both GeoDataFrames
        all_polys_gdf = pd.concat([isochrone_gdf, intersection_gdf], ignore_index=True)
        all_polys_gdf = gpd.GeoDataFrame(all_polys_gdf, crs="EPSG:27700")
        all_polys_gdf = all_polys_gdf.to_crs("EPSG:4326")

        # Build color map dynamically
        query_colors = ["blue", "green", "orange", "purple", "cyan", "magenta"]
        color_discrete_map = {"Intersection": "red"}
        for i in range(len(other_polys)):
            color_discrete_map[f"Query {i}"] = query_colors[i % len(query_colors)]

        fig = px.choropleth_map(
            all_polys_gdf,
            geojson=all_polys_gdf.geometry.__geo_interface__,
            locations=all_polys_gdf.index,
            color="type",
            color_discrete_map=color_discrete_map,
            center={
                "lat": all_polys_gdf.geometry.centroid.y.mean(),
                "lon": all_polys_gdf.geometry.centroid.x.mean(),
            },
            zoom=11,
            opacity=0.5,
        )
        st.plotly_chart(fig, width="stretch")
