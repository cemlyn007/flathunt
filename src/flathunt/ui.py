import asyncio
import logging
from collections.abc import Iterable

import geopandas as gpd
import pandas as pd
import plotly.express as px
import streamlit as st
from shapely.geometry import Point

import rightmove.api
import rightmove.models
import rightmove.price
from flathunt.isochrone import (
    get_intersection,
    get_isochone_polys,
    load_graph,
    multi_lookup,
)
from flathunt.search_utils import check_property_size, get_properties, get_property_ids

logger = logging.getLogger("flathunt")


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
                columns=["Longitude", "Latitude", "Max Duration"],
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
            graph = load_graph(offset)
            isochrone_subgraphs = multi_lookup(graph, queries)
            isochrone_polys = get_isochone_polys(isochrone_subgraphs)
            groups = []
            for subgraphs, polys in zip(
                isochrone_subgraphs, isochrone_polys, strict=True
            ):
                groups.append((subgraphs, polys))
            polys, intersection_graphs = get_intersection(graph, groups)
        st.status("Completed processing query.", state="complete")
        st.session_state["isochrone_graphs"] = isochrone_subgraphs
        st.session_state["isochrone_polys"] = isochrone_polys
        st.session_state["intersection_polys"] = polys
        st.session_state["intersection_graphs"] = intersection_graphs


def render_map_section() -> None:
    if (
        "intersection_graphs" in st.session_state
        and "intersection_polys" in st.session_state
        and "isochrone_graphs" in st.session_state
        and "isochrone_polys" in st.session_state
        and "queries" in st.session_state
    ):
        polys = st.session_state["intersection_polys"]
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


def render_property_search_section() -> tuple[int, int] | tuple[None, None]:
    if "intersection_polys" not in st.session_state:
        return None, None

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
    if list_property_ids:
        polys = st.session_state["intersection_polys"]
        intersection_graphs = st.session_state["intersection_graphs"]
        property_ids = asyncio.run(
            get_property_ids(
                polys, intersection_graphs, st.session_state.get("queries", [])
            )
        )
        st.write(f"Found {len(property_ids)} properties in the area.")
        properties = asyncio.run(get_properties(property_ids))
        st.session_state["properties"] = properties

    return min_budget, max_budget


def render_results_section(min_budget: int, max_budget: int) -> None:
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
        filtered_properties = filter_properties_by_criteria(
            properties,
            min_budget,
            max_budget,
            has_floorplans,
            has_images,
            square_meters,
        )
        st.write(f"{len(filtered_properties)} properties match the criteria.")
        render_property_table(filtered_properties)


def filter_properties_by_criteria(
    properties: Iterable[rightmove.models.Property],
    min_budget: float,
    max_budget: float,
    has_floorplans: bool,
    has_images: bool,
    square_meters: float,
):
    filtered_properties = [
        property
        for property in properties
        if property.property_url is not None
        and check_property_size(property, square_meters)
        and property.price is not None
        and min_budget <= (rightmove.price.normalize(property.price) or 0) <= max_budget
        and ((property.number_of_images or 0) > 2 or not has_images)
        and ((property.number_of_floorplans or 0) > 0 or not has_floorplans)
    ]

    return filtered_properties


def render_property_table(
    filtered_properties: list[rightmove.models.Property],
) -> None:
    property_data = []
    for property in filtered_properties:
        if property.property_url is None:
            continue
        normalized_price = (
            rightmove.price.normalize(property.price) if property.price else None
        )
        property_data.append(
            {
                "Name": property.display_address or "N/A",
                "Price": f"£{normalized_price:,}" if normalized_price else "N/A",
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
