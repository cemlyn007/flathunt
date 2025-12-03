import asyncio
import concurrent.futures
import datetime
import itertools
import logging
import os
import pickle
from collections.abc import Collection, Hashable
from pathlib import Path
from typing import Literal

import dotenv
import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
import tqdm
import tqdm.asyncio
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon

import rightmove.api
import rightmove.models
import tfl.api
import tfl.models

logger = logging.getLogger("flathunt")
logging.basicConfig(level=logging.INFO)

dotenv.load_dotenv()


NODE_BUFFER = 0
EDGE_BUFFER = 25
TARGET_DATETIME = tfl.api.get_next_datetime(
    datetime.time(9, 0, 0, tzinfo=datetime.timezone.utc)
)
MAX_RIGHTMOVE_POLYLINE_POINTS = 1000
MAX_RIGHTMOVE_SEARCH_PROPERTIES = 499
MAX_RIGHTMOVE_GET_PROPERTIES = 25


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
    with concurrent.futures.ThreadPoolExecutor() as executor:
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


def _get_intersection(
    graph: nx.Graph, groups: list[tuple[list[nx.Graph], list[Polygon]]]
) -> tuple[list[Polygon], list[nx.Graph]]:
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
                node_attributes.update(graph.nodes[node_id])
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
        polys, subgraphs = _get_intersection(graph, rest)
        return _get_intersection(graph, [group, (subgraphs, polys)])


def load_graph(station_cost: float) -> nx.Graph:
    graph = pickle.loads(Path(".dagster/storage/roads_and_transport").read_bytes())
    for n_fr, n_to in graph.edges():
        if "station_name" in graph.nodes[n_fr] or "station_name" in graph.nodes[n_to]:
            graph.edges[n_fr, n_to]["duration"] += station_cost
    return graph


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


async def get_property_ids(
    polys: list[Polygon],
    graphs: list[nx.Graph],
    queries: list[tuple[float, float, float]],
    channel: Literal["RENT", "BUY"] = "RENT",
) -> set[int]:
    min_times = {}

    tf_client = tfl.api.Tfl(app_key=os.environ["FLATHUNT__TFL_API_KEY"])

    check_coords = []
    for poly, poly_network in zip(polys, graphs, strict=True):
        if poly.is_empty:
            continue
        x, y = poly.centroid.x, poly.centroid.y
        for node_id, node_attributes in poly_network.nodes(data=True):
            if "station_name" in node_attributes:
                print(f"Station in intersection: {node_attributes['station_name']}")
                x = node_attributes["x"]
                y = node_attributes["y"]
        lon, lat = (
            gpd.GeoSeries([Point(x, y)], crs="EPSG:27700")
            .to_crs("EPSG:4326")
            .geometry[0]
            .coords[0]
        )
        check_coords.append((lon, lat))

    async def fetch_journey_results(lon, lat, query_lon, query_lat, i):
        try:
            journey_results = await tf_client.get_journey_results(
                from_location=(lat, lon),
                to_location=(query_lat, query_lon),
                arrival_datetime=TARGET_DATETIME,
                modes=[
                    tfl.models.ModeId.TUBE,
                    tfl.models.ModeId.OVERGROUND,
                    tfl.models.ModeId.DLR,
                    tfl.models.ModeId.ELIZABETH_LINE,
                    tfl.models.ModeId.WALKING,
                ],
                use_multi_modal_call=False,
            )
            if isinstance(journey_results, tfl.models.DisambiguationResult):
                logger.error(
                    "Disambiguation result for journey from (%s, %s) to (%s, %s)",
                    lon,
                    lat,
                    query_lon,
                    query_lat,
                )
                return None, None
            min_time = min(journey.duration for journey in journey_results.journeys)
            return (lon, lat), (query_lon, query_lat, min_time)
        except Exception:
            logger.exception(
                "Exception fetching journey from (%s, %s) to (%s, %s)",
                lon,
                lat,
                query_lon,
                query_lat,
            )
            return None, None

    tasks = []
    for lon, lat in tqdm.tqdm(check_coords):
        for i, (query_lon, query_lat, _) in enumerate(queries):
            tasks.append(fetch_journey_results(lon, lat, query_lon, query_lat, i))

    async for future in tqdm.asyncio.tqdm(
        asyncio.as_completed(tasks), total=len(tasks)
    ):
        result = await future
        if result[0] is not None and result[1] is not None:
            (lon, lat), (query_lon, query_lat, min_time) = result
            min_times.setdefault((lon, lat), {})[(query_lon, query_lat)] = min_time

    best_coords = []
    for poly in polys:
        if poly.is_empty:
            continue

        exterior, tolerance = find_min_simplify_tolerance(poly, max_coords=1000)

        meters = list(exterior.coords)
        coords = []
        for x, y in meters:
            lon, lat = (
                gpd.GeoSeries([Point(x, y)], crs="EPSG:27700")
                .to_crs("EPSG:4326")
                .geometry[0]
                .coords[0]
            )
            coords.append((lat, lon))
        best_coords.append(coords)

    rightmove_client = rightmove.api.Rightmove()
    all_property_ids = set()
    for coord, coords in tqdm.tqdm(zip(min_times, best_coords), total=len(best_coords)):
        if len(coords) > MAX_RIGHTMOVE_POLYLINE_POINTS:
            raise ValueError(
                f"Rightmove accepts polygons with up to {MAX_RIGHTMOVE_POLYLINE_POINTS} points."
            )
        search_results, count = await rightmove_client.map_search(
            rightmove.api.SearchQuery(
                location_identifier=rightmove.api.polyline_identifier(coords),
                is_fetching=True,
                view_type="MAP",
                channel=channel,
            )
        )
        if count > MAX_RIGHTMOVE_SEARCH_PROPERTIES:
            st.warning(
                f"Warning: Rightmove returned {count} results for polygon around {coord}, which exceeds the maximum of {MAX_RIGHTMOVE_SEARCH_PROPERTIES}. Some properties may be missing."
            )
        all_property_ids.update(property.id for property in search_results)
    return all_property_ids


async def get_properties(
    property_ids: Collection[int],
    channel: Literal["RENT", "BUY"] = "RENT",
    show_errors_in_ui: bool = False,
) -> list[rightmove.models.Property]:
    rightmove_client = rightmove.api.Rightmove()
    property_results: list[rightmove.models.Property] = []
    with tqdm.tqdm(total=len(property_ids)) as pbar:
        for apids in itertools.batched(property_ids, MAX_RIGHTMOVE_GET_PROPERTIES):
            try:
                property_results.extend(
                    await rightmove_client.search_by_ids(apids, channel=channel)
                )
            except Exception:
                for apid in apids:
                    try:
                        props = await rightmove_client.search_by_ids(
                            [apid], channel=channel
                        )
                        property_results.extend(props)
                    except Exception:
                        logger.exception("Exception fetching property ID %s", apid)
                        if show_errors_in_ui:
                            st.error(f"Error fetching property ID {apid}")
            pbar.update(len(apids))
    return property_results


def check_property_size(property: rightmove.models.Property, min_square_meters: float):
    if property.display_size:
        if property.display_size.endswith(" sq. ft."):
            square_ft = int(
                property.display_size.removesuffix(" sq. ft.").replace(",", "")
            )
            square_meters = int(square_ft * 0.092903)
            if square_meters < min_square_meters:
                return False
        elif property.display_size.endswith(" sqm"):
            square_meters = int(
                property.display_size.removesuffix(" sqm").replace(",", "")
            )
            if square_meters < min_square_meters:
                return False
    return True


def get_isochone_polys(
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
                else:
                    queries.append(query)
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

    # Keep the offset in-line with dagster:
    offset = st.slider(
        "Station Cost Offset (in minutes):",
        min_value=-4,
        max_value=30,
        value=0,
        key="station_cost_offset_slider",
    )
    process = st.button("Get Isochrones", key="process_queries_button")
    if process and (queries := st.session_state.get("queries", [])):
        with st.spinner("Processing..."):
            graph = load_graph(offset)
            isochrone_subgraphs = multi_lookup(graph, queries)
            isochrone_polys = get_isochone_polys(isochrone_subgraphs)
            groups = []
            for subgraphs, polys in zip(
                isochrone_subgraphs, isochrone_polys, strict=True
            ):
                groups.append((subgraphs, polys))
            polys, intersection_graphs = _get_intersection(graph, groups)
        st.status("Completed processing query.", state="complete")
        st.session_state["isochrone_graphs"] = isochrone_subgraphs
        st.session_state["isochrone_polys"] = isochrone_polys
        st.session_state["intersection_polys"] = polys
        st.session_state["intersection_graphs"] = intersection_graphs

    if (
        "intersection_graphs" in st.session_state
        and "intersection_polys" in st.session_state
        and "isochrone_graphs" in st.session_state
        and "isochrone_polys" in st.session_state
        and "queries" in st.session_state
    ):
        intersection_graphs = st.session_state["intersection_graphs"]
        polys = st.session_state["intersection_polys"]
        isochrone_subgraphs = st.session_state["isochrone_graphs"]
        isochrone_polys = st.session_state["isochrone_polys"]
        queries = st.session_state["queries"]
        # Make map
        if len(queries) == 1:
            other_polys = []
        else:
            other_polys = isochrone_polys
        polys = [poly for poly in polys if not poly.is_empty]
        st.write(f"Found {len(polys)} intersection graphs.")

        logger.info("Plotting map of isochrones and intersections.")

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

        # Calculate centroid in projected CRS before converting to WGS84
        center_lat = all_polys_gdf.geometry.centroid.y.mean()
        center_lon = all_polys_gdf.geometry.centroid.x.mean()
        center_point = gpd.GeoSeries([Point(center_lon, center_lat)], crs="EPSG:27700")
        center_point_wgs84 = center_point.to_crs("EPSG:4326")

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
                "lat": center_point_wgs84.y.iloc[0],
                "lon": center_point_wgs84.x.iloc[0],
            },
            zoom=11,
            opacity=0.5,
        )
        st.plotly_chart(fig, use_container_width=True)

        st.header("Search Properties in Intersection Area")
        st.write(
            "These settings effect the search and will require re-fetching property IDs."
        )
        min_budget, max_budget = st.slider(
            "Set your monthly budget for filtering properties:",
            min_value=500,
            max_value=10000,
            value=(1900, 2250),
            step=50,
            key="budget_slider",
        )
        list_property_ids = st.button(
            "Get property IDs in area", key="get_property_ids_button"
        )
        if list_property_ids and "intersection_polys" in st.session_state:
            polys = st.session_state["intersection_polys"]
            intersection_graphs = st.session_state["intersection_graphs"]

            # TODO: Sometimes the polygon is so large that it needs to be subdivided
            #  if you want to get all of the properties.
            property_ids = asyncio.run(
                get_property_ids(
                    polys, intersection_graphs, st.session_state.get("queries", [])
                )
            )
            st.write(f"Found {len(property_ids)} properties in the area.")
            properties = asyncio.run(get_properties(property_ids))
            st.session_state["properties"] = properties

        logger.info("Finished execution of flathunt.py")

        if "properties" in st.session_state:
            st.subheader("Extra Filters")
            has_floorplans = st.checkbox(
                "Only show properties with floorplans",
                key="floorplan_checkbox",
                value=True,
            )
            has_images = st.checkbox(
                "Only show properties with images", key="images_checkbox", value=True
            )
            square_meters = st.slider(
                "Minimum property size (in square meters):",
                min_value=10,
                max_value=200,
                value=60,
                key="size_slider",
            )
            properties = st.session_state["properties"]
            filtered_properties = [
                property
                for property in properties
                if property.property_url is not None
                and check_property_size(property, square_meters)
                and property.price is not None
                and min_budget
                <= (rightmove.price.normalize(property.price) or 0)
                <= max_budget
                and ((property.number_of_images or 0) > 2 or not has_images)
                and ((property.number_of_floorplans or 0) > 0 or not has_floorplans)
            ]
            st.write(f"{len(filtered_properties)} properties match the criteria.")
            property_data = []
            for property in filtered_properties:
                normalized_price = (
                    rightmove.price.normalize(property.price)
                    if property.price
                    else None
                )
                property_data.append(
                    {
                        "Name": property.display_address or "N/A",
                        "Price": f"£{normalized_price:,}"
                        if normalized_price
                        else "N/A",
                        "Size": property.display_size or "N/A",
                        "URL": rightmove.api.property_url(property.property_url),
                    }
                )
            st.dataframe(
                property_data,
                column_config={
                    "URL": st.column_config.LinkColumn("URL"),
                },
                width="stretch",
            )
