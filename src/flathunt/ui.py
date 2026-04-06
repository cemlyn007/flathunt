import asyncio
import concurrent.futures
import json
import logging
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, cast

import geopandas as gpd
import pandas as pd
import plotly.express as px
import streamlit as st
from shapely import GeometryCollection, Point, Polygon

import rightmove.models
from flathunt.cache import ModelCache
from flathunt.isochrone import (
    EDGE_BUFFER,
    NODE_BUFFER,
    bounds_to_polygon,
    get_intersection,
    load_graph,
    lookup,
    make_poly,
)
from flathunt.property_search import (
    filter_by_commute,
    filter_properties_by_budget_and_features,
    get_commute_durations,
    get_property_ids_in_area_cached,
)

logger = logging.getLogger("flathunt")

data_dir = Path(st.secrets["cache"]["data_dir"])

tfl_api_key = st.secrets["tfl"]["api_key"]

if not st.session_state.get("initialized", False):
    data_dir.mkdir(parents=True, exist_ok=True)
    st.session_state["queries"] = json.loads(os.environ["FLATHUNT__QUERIES"])
    st.session_state["initialized"] = True


@st.cache_resource
def get_property_ids_in_area_cache() -> ModelCache[list[rightmove.models.MapProperty]]:
    cache = data_dir / "property_locations_cache.json"
    if cache.exists():
        graph_path = Path(".dagster/storage/roads_and_transport")
        if graph_path.exists() and cache.stat().st_mtime < graph_path.stat().st_mtime:
            cache.unlink()
    return ModelCache(
        list[rightmove.models.MapProperty],
        cache,
    )


@st.cache_resource
def get_journey_cache() -> ModelCache[int | None]:
    cache = data_dir / "journey_cache.json"
    if cache.exists():
        graph_path = Path(".dagster/storage/roads_and_transport")
        if graph_path.exists() and cache.stat().st_mtime < graph_path.stat().st_mtime:
            cache.unlink()
    return ModelCache(int | None, cache)  # type: ignore



@st.cache_data(persist="disk")
def _process_isochrone_data(
    queries: Sequence[tuple[float, float, float]], offset: int
) -> tuple[list[Polygon], list[list[Polygon]]]:
    graph = load_graph(offset)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        separate_isochrones = list(
            executor.map(
                lookup,
                [graph] * len(queries),
                [q[0] for q in queries],
                [q[1] for q in queries],
                [q[2] for q in queries],
            )
        )
        polys_futures = [
            [
                executor.submit(make_poly, sg, EDGE_BUFFER, NODE_BUFFER)
                for sg in subgraphs
            ]
            for subgraphs in separate_isochrones
        ]
        intersection_graphs = get_intersection(
            graph, separate_isochrones, executor=executor
        )
        intersections_polys_futures = [
            executor.submit(make_poly, sg, EDGE_BUFFER, NODE_BUFFER)
            for sg in intersection_graphs
        ]
        isochrone_polys = [
            [future.result() for future in poly_futures]
            for poly_futures in polys_futures
        ]
        polys = [future.result() for future in intersections_polys_futures]
    return polys, isochrone_polys




def render_query_section() -> None:
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
                columns=["Longitude", "Latitude", "Max Duration"],  # type: ignore
            )
        )
        st.button("Clear queries", on_click=lambda: st.session_state.pop("queries"))


def render_isochrone_section() -> None:
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
        with st.spinner("Processing...", show_time=True):
            intersection_isochrone_polys, isochrone_polys = _process_isochrone_data(
                tuple(queries), offset
            )
        st.status("Completed processing query.", state="complete")
        st.session_state["isochrone_polys"] = isochrone_polys
        st.session_state["intersection_polys"] = intersection_isochrone_polys


def render_map_section() -> None:
    if (
        "intersection_polys" in st.session_state
        and "isochrone_polys" in st.session_state
        and "queries" in st.session_state
    ):
        polys = st.session_state["intersection_polys"]
        isochrone_polys = st.session_state["isochrone_polys"]
        queries = st.session_state["queries"]
        fig = _get_map(
            tuple(queries),
            tuple(polys),
            tuple(tuple(poly for poly in poly_list) for poly_list in isochrone_polys),
        )
        st.plotly_chart(fig, use_container_width=True)


def render_property_search_section() -> None:
    if "intersection_polys" not in st.session_state:
        return

    st.header("Search Properties in Intersection Area")
    last_channel = st.session_state.get("channel_selectbox", None)
    channel = st.selectbox("Select channel:", ["RENT", "BUY"], key="channel_selectbox")
    if channel != "RENT" and channel != "BUY":
        st.error("Invalid channel selected.")
        return
    channel = cast(Literal["RENT", "BUY"], channel)
    if last_channel != channel:
        if "properties" in st.session_state:
            del st.session_state["properties"]
    list_property_ids = st.button(
        "Get property IDs in area", key="get_property_ids_button"
    )
    if list_property_ids:
        polys = st.session_state["intersection_polys"]
        property_locations: list[rightmove.models.MapProperty] = []
        graph = load_graph(0)
        bounding_polygon = bounds_to_polygon(
            (
                min(data["lon"] for data in graph.nodes.values()),
                min(data["lat"] for data in graph.nodes.values()),
                max(data["lon"] for data in graph.nodes.values()),
                max(data["lat"] for data in graph.nodes.values()),
            )
        )
        for poly in polys:
            if poly.is_empty:
                continue
            xs, ys = poly.exterior.coords.xy
            # Convert from British National Grid (EPSG:27700) to WGS84 (EPSG:4326)
            points_bng = gpd.GeoSeries(
                [Point(x, y) for x, y in zip(xs, ys, strict=True)], crs="EPSG:27700"
            )
            points_wgs84 = points_bng.to_crs("EPSG:4326")
            lon = [point.x for point in points_wgs84]  # pyright: ignore[reportAttributeAccessIssue]
            lat = [point.y for point in points_wgs84]  # pyright: ignore[reportAttributeAccessIssue]
            coords = list(zip(lat, lon, strict=True))
            property_locations.extend(
                get_property_ids_in_area_cached(
                    bounding_polygon, coords, channel, get_property_ids_in_area_cache()
                )
            )

        # Convert intersection polygons from EPSG:27700 to WGS84 for point-in-polygon
        # checks against property locations (which are in WGS84 lat/lon).
        polys_wgs84 = []
        for poly in polys:
            if poly.is_empty:
                continue
            converted = gpd.GeoSeries([poly], crs="EPSG:27700").to_crs("EPSG:4326")
            if len(converted) != 1:
                raise ValueError(
                    f"Expected 1 geometry after reprojection, got {len(converted)}"
                )
            polys_wgs84.append(converted.iloc[0])
        property_locations = [
            loc
            for loc in property_locations
            if any(
                p.contains(Point(loc.location.longitude, loc.location.latitude))
                for p in polys_wgs84
            )
        ]
        st.write(f"Found {len(property_locations)} unfiltered properties in the area.")
        queries = st.session_state["queries"]
        durations = asyncio.run(
            get_commute_durations(property_locations, queries, get_journey_cache(), tfl_api_key)
        )
        filtered = filter_by_commute(property_locations, durations, queries)
        st.write(
            f"Found {len(filtered)} properties in the area within commute criteria."
        )
        st.session_state["properties"] = [p for p, _ in filtered]



def render_results_section() -> None:
    if "properties" in st.session_state:
        st.subheader("Extra Filters")
        channel = st.session_state["channel_selectbox"]
        if channel == "RENT":
            min_budget, max_budget = st.slider(
                "Set your monthly budget for filtering properties:",
                min_value=500,
                max_value=10000,
                value=(1900, 2250),
                step=50,
                key="budget_slider",
            )
        elif channel == "BUY":
            min_budget, max_budget = st.slider(
                "Set your property value for filtering properties:",
                min_value=100000,
                max_value=2000000,
                value=(300000, 600000),
                step=10000,
                key="budget_slider",
            )
        else:
            st.error("Invalid channel selected.")
            return
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
        candidates = filter_properties_by_budget_and_features(
            properties,
            min_budget,
            max_budget,
            has_floorplans,
            has_images,
            square_meters,
            channel,
        )
        queries = st.session_state["queries"]
        durations = asyncio.run(
            get_commute_durations(candidates, queries, get_journey_cache(), tfl_api_key)
        )
        filtered = filter_by_commute(candidates, durations, queries)
        st.write(f"{len(filtered)} properties match the criteria.")
        render_property_table(filtered, queries)



def render_property_table(
    filtered: list[tuple[rightmove.models.MapProperty, list[int | None]]],
    queries: list[tuple[float, float, float]],
) -> None:
    property_data = []
    channel = st.session_state["channel_selectbox"]
    for property, prop_durations in filtered:
        if property.property_url is None:
            continue
        if channel == "RENT":
            normalized_price = (
                rightmove.price.normalize(property.price) if property.price else None
            )
        else:
            normalized_price = property.price.amount if property.price else None
        commute_durations = {
            f"Commute to Query {i + 1}": (
                f"{d} mins" if d is not None else "N/A"
            )
            for i, d in enumerate(prop_durations)
        }
        commute_values = [d for d in prop_durations if d is not None]
        property_data.append(
            {
                "Name": property.display_address or "N/A",
                "Price": f"£{normalized_price:,}" if normalized_price else "N/A",
                "Size": property.display_size or "N/A",
                "URL": rightmove.api.property_url(property.property_url),
                "Minutes to Commute": max(commute_values) if commute_values else "N/A",
                **commute_durations,
            }
        )
    st.dataframe(
        property_data,
        column_config={
            "URL": st.column_config.LinkColumn("URL"),
        },
        width="stretch",
    )


@st.cache_data(
    hash_funcs={
        Polygon: lambda poly: poly.wkt,
        GeometryCollection: lambda poly: poly.wkt,
    }
)
def _get_geo_dataframe(
    polys: tuple[Polygon, ...],
    other_polys: tuple[tuple[Polygon | GeometryCollection, ...], ...],
) -> tuple[gpd.GeoDataFrame, gpd.GeoSeries]:
    # Build GeoDataFrame for intersection polygons
    intersection_gdf = gpd.GeoDataFrame(
        {"id": list(range(len(polys))), "type": ["Intersection"] * len(polys)},
        geometry=list(polys),
        crs="EPSG:27700",
    )

    # Build GeoDataFrame for isochrone polygons (flattened)
    isochrone_polys_flat = []
    isochrone_ids = []
    isochrone_types = []
    for i, poly_list in enumerate(other_polys):
        for poly in poly_list:
            if not poly.is_empty:
                isochrone_polys_flat.append(poly)
                isochrone_ids.append(f"isochrone_{i}")
                isochrone_types.append(f"Query {i}")

    isochrone_gdf = gpd.GeoDataFrame(
        {"id": isochrone_ids, "type": isochrone_types},
        geometry=isochrone_polys_flat,
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

    all_polys_gdf.geometry = all_polys_gdf.geometry.simplify(tolerance=10)
    all_polys_gdf = all_polys_gdf.to_crs("EPSG:4326")
    return all_polys_gdf, center_point_wgs84


@st.cache_data(
    hash_funcs={
        Polygon: lambda poly: poly.wkt,
        GeometryCollection: lambda poly: poly.wkt,
    }
)
def _get_map(
    queries: tuple[tuple[float, float, float], ...],
    polys: tuple[Polygon, ...],
    isochrone_polys: tuple[tuple[Polygon | GeometryCollection, ...], ...],
):
    # Make map
    if len(queries) == 1:
        other_polys = []
    else:
        other_polys = isochrone_polys
    non_empty_polys = [poly for poly in polys if not poly.is_empty]
    st.write(f"Found {len(non_empty_polys)} intersection graphs.")
    all_polys_gdf, center_point_wgs84 = _get_geo_dataframe(
        tuple(non_empty_polys), tuple(tuple(poly) for poly in other_polys)
    )
    return _get_choropleth_map_figure(
        all_polys_gdf,
        center_point_wgs84.y.iloc[0],
        center_point_wgs84.x.iloc[0],
        len(other_polys),
    )


def _get_choropleth_map_figure(
    all_polys_gdf: gpd.GeoDataFrame,
    center_lat: float,
    center_lon: float,
    num_other_polys: int,
):
    logger.info("Plotting map of isochrones and intersections.")
    # Build color map dynamically
    query_colors = ["blue", "green", "orange", "purple", "cyan", "magenta"]
    color_discrete_map = {"Intersection": "red"}
    for i in range(num_other_polys):
        color_discrete_map[f"Query {i}"] = query_colors[i % len(query_colors)]
    return px.choropleth_map(
        all_polys_gdf,
        geojson=all_polys_gdf.geometry.__geo_interface__,
        locations=all_polys_gdf.index,
        color="type",
        color_discrete_map=color_discrete_map,
        center={
            "lat": center_lat,
            "lon": center_lon,
        },
        zoom=11,
        opacity=0.5,
    )
