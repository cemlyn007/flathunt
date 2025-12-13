import asyncio
import json
import logging
import os
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Literal

import geopandas as gpd
import pandas as pd
import plotly.express as px
import streamlit as st
from shapely import GeometryCollection, Polygon
from shapely.geometry import Point

import rightmove.api
import rightmove.models
import rightmove.price
import tfl.api
from flathunt.cache import ModelCache
from flathunt.isochrone import (
    get_intersection,
    get_isochrone_polys,
    load_graph,
    multi_lookup,
)
from flathunt.search_utils import (
    check_property_size,
    fetch_journey_results,
    get_properties,
    get_property_ids_in_area,
)

logger = logging.getLogger("flathunt")

data_dir = Path(st.secrets["cache"]["data_dir"])

if not st.session_state.get("initialized", False):
    data_dir.mkdir(parents=True, exist_ok=True)
    st.session_state["queries"] = json.loads(os.environ["FLATHUNT__QUERIES"])
    st.session_state["initialized"] = True


@st.cache_resource
def get_property_ids_in_area_cache() -> ModelCache[
    list[rightmove.models.PropertyLocation]
]:
    return ModelCache(
        list[rightmove.models.PropertyLocation],
        data_dir / "property_locations_cache.json",
    )


@st.cache_resource
def get_journey_cache() -> ModelCache[int | None]:
    return ModelCache(int | None, data_dir / "journey_cache.json")


@st.cache_resource
def get_property_cache() -> ModelCache[rightmove.models.Property]:
    return ModelCache(rightmove.models.Property, data_dir / "property_cache.json")


def _get_property_ids_in_area_cached(
    coords: list[tuple[float, float]], channel: Literal["RENT", "BUY"] = "RENT"
) -> list[rightmove.models.PropertyLocation]:
    cache = get_property_ids_in_area_cache()
    key = json.dumps({"coords": coords, "channel": channel})
    try:
        property_locations = cache.get(key)
        logger.info("Property IDs fetched from cache.")
        return property_locations
    except KeyError:
        property_locations = []
        logger.info("Property IDs not found in cache, fetching from Rightmove.")
    property_ids_in_area = asyncio.run(
        get_property_ids_in_area(coords, channel=channel)
    )
    cache.update([(key, property_ids_in_area)])
    return property_locations + property_ids_in_area


async def _get_properties_journey_duration_cached(
    to_froms: list[tuple[float, float, float, float]],
) -> list[int | None]:
    # lon: float, lat: float, query_lon: float, query_lat: float
    cache = get_journey_cache()
    durations = []
    to_fetch = []
    fetch_indices = []
    for i, (lon, lat, query_lon, query_lat) in enumerate(to_froms):
        key = json.dumps(
            {"from": (lon, lat), "to": (query_lon, query_lat)},
        )
        try:
            duration = cache.get(key)
            durations.append(duration)
            logger.info(
                "Journey duration from (%s, %s) to (%s, %s) fetched from cache.",
                lon,
                lat,
                query_lon,
                query_lat,
            )
        except KeyError:
            to_fetch.append((lon, lat, query_lon, query_lat))
            fetch_indices.append(i)
            durations.append(None)  # Placeholder
    if to_fetch:
        client = tfl.api.Tfl(app_key=os.environ["FLATHUNT__TFL_API_KEY"])
        tasks = [
            fetch_journey_results(client, lon, lat, query_lon, query_lat)
            for lon, lat, query_lon, query_lat in to_fetch
        ]
        results = await asyncio.gather(*tasks)
        cache_updates = []
        for idx, duration in zip(fetch_indices, results):
            durations[idx] = duration
            lon, lat, query_lon, query_lat = to_froms[idx]
            key = json.dumps(
                {"from": (lon, lat), "to": (query_lon, query_lat)},
            )
            cache_updates.append((key, duration))
        cache.update(cache_updates)
    return durations


def _get_properties(
    property_ids: list[int], channel: Literal["RENT", "BUY"] = "RENT"
) -> list[rightmove.models.Property]:
    found_properties = []
    missing_ids = []
    cache = get_property_cache()
    for property_id in property_ids:
        try:
            property = cache.get(json.dumps({"id": property_id, "channel": channel}))
            found_properties.append(property)
        except KeyError:
            missing_ids.append(property_id)

    if missing_ids:
        logger.info(f"Fetching {len(missing_ids)} properties from Rightmove...")
        new_properties = asyncio.run(get_properties(missing_ids))
        cache.update(
            (json.dumps({"id": property.id, "channel": channel}), property)
            for property in new_properties
        )
        found_properties.extend(new_properties)

    return found_properties


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
            isochrone_subgraphs, isochrone_polys, polys, intersection_graphs = (
                _process_isochrone_data(tuple(queries), offset)
            )
        st.status("Completed processing query.", state="complete")
        st.session_state["isochrone_graphs"] = isochrone_subgraphs
        st.session_state["isochrone_polys"] = isochrone_polys
        st.session_state["intersection_polys"] = polys
        st.session_state["intersection_graphs"] = intersection_graphs


@st.cache_data
def _process_isochrone_data(queries: Sequence[tuple[float, float, float]], offset: int):
    graph = load_graph(offset)
    isochrone_subgraphs = multi_lookup(graph, queries)
    isochrone_polys = get_isochrone_polys(isochrone_subgraphs)
    groups = []
    for subgraphs, polys in zip(isochrone_subgraphs, isochrone_polys, strict=True):
        groups.append((subgraphs, polys))
    polys, intersection_graphs = get_intersection(graph, groups)
    return isochrone_subgraphs, isochrone_polys, polys, intersection_graphs


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

        all_polys_gdf, center_point_wgs84 = _get_geo_dataframe(
            tuple(polys), tuple(tuple(poly) for poly in other_polys)
        )

        logger.info("Plotting map of isochrones and intersections.")
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


def render_property_search_section() -> None:
    if "intersection_polys" not in st.session_state:
        return

    st.header("Search Properties in Intersection Area")
    list_property_ids = st.button(
        "Get property IDs in area", key="get_property_ids_button"
    )
    if list_property_ids:
        polys = st.session_state["intersection_polys"]
        property_locations: list[rightmove.models.PropertyLocation] = []
        for poly in polys:
            if poly.is_empty:
                continue
            xs, ys = poly.exterior.coords.xy
            # Convert from British National Grid (EPSG:27700) to WGS84 (EPSG:4326)
            points_bng = gpd.GeoSeries(
                [Point(x, y) for x, y in zip(xs, ys, strict=True)], crs="EPSG:27700"
            )
            points_wgs84 = points_bng.to_crs("EPSG:4326")
            lon = [point.x for point in points_wgs84]
            lat = [point.y for point in points_wgs84]
            coords = list(zip(lat, lon, strict=True))
            property_locations.extend(
                _get_property_ids_in_area_cached(coords, channel="RENT")
            )
        property_ids = [location.id for location in property_locations]
        st.write(f"Found {len(property_ids)} properties in the area.")
        st.session_state["properties"] = _get_properties(property_ids, channel="RENT")


def render_results_section() -> None:
    if "properties" in st.session_state:
        st.subheader("Extra Filters")
        min_budget, max_budget = st.slider(
            "Set your monthly budget for filtering properties:",
            min_value=500,
            max_value=10000,
            value=(1900, 2250),
            step=50,
            key="budget_slider",
        )
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
    queries = st.session_state["queries"]
    commute_times = asyncio.run(
        _get_properties_journey_duration_cached(
            [
                (
                    property.location.longitude,
                    property.location.latitude,
                    query_lon,
                    query_lat,
                )
                for property in filtered_properties
                for query_lon, query_lat, _ in queries
            ]
        )
    )
    final_filtered_properties = []
    for i, property in enumerate(filtered_properties):
        meets_commute = True
        for j in range(len(queries)):
            duration = commute_times[i * len(queries) + j]
            max_duration = queries[j][2]
            if duration is None or duration > max_duration:
                meets_commute = False
                break
        if meets_commute:
            final_filtered_properties.append(property)
    return final_filtered_properties


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
        commute_durations = {}
        commute_values = []
        queries = st.session_state["queries"]
        for index, (query_lon, query_lat, _) in enumerate(queries):
            (duration,) = asyncio.run(
                _get_properties_journey_duration_cached(
                    [
                        (
                            property.location.longitude,
                            property.location.latitude,
                            query_lon,
                            query_lat,
                        )
                    ]
                )
            )
            if duration is not None:
                commute_values.append(duration)
            commute_durations["Commute to Query {}".format(index + 1)] = (
                f"{duration} mins" if duration is not None else "N/A"
            )

        property_data.append(
            {
                "Name": property.display_address or "N/A",
                "Price": f"£{normalized_price:,}" if normalized_price else "N/A",
                "Size": property.display_size or "N/A",
                "URL": rightmove.api.property_url(property.property_url),
                "Minutes to Commute": min(commute_values) if commute_values else "N/A",
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

    all_polys_gdf = all_polys_gdf.to_crs("EPSG:4326")
    return all_polys_gdf, center_point_wgs84
