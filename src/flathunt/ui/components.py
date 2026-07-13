import asyncio
import concurrent.futures
import logging
import os
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Literal

import geopandas as gpd
import pandas as pd
import plotly.express as px
import pydantic
import streamlit as st
from shapely import GeometryCollection, Point, Polygon

import rightmove.models
from flathunt.cache import ModelCache
from flathunt.coords import CommuteDest
from flathunt.filters import (
    filter_by_commute,
    filter_properties_by_budget_and_features,
)
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
    DEFAULT_JOURNEY_CACHE_TTL,
    DEFAULT_PROPERTY_TILE_CACHE_RETENTION_TTL,
    fetch_properties_within_optimal_regions,
    get_commute_durations,
)

logger = logging.getLogger("flathunt")

data_dir = Path(st.secrets["cache"]["data_dir"])

tfl_api_key = st.secrets["tfl"]["api_key"]

if not st.session_state.get("initialized", False):
    data_dir.mkdir(parents=True, exist_ok=True)
    st.session_state["queries"] = pydantic.TypeAdapter(list[CommuteDest]).validate_json(
        os.environ["FLATHUNT__QUERIES"]
    )
    st.session_state["initialized"] = True


# ==============================================================================
# CACHE MANAGEMENT
# ==============================================================================


@st.cache_resource
def get_property_ids_in_area_cache() -> ModelCache[list[rightmove.models.MapProperty]]:
    """Return the Streamlit-cached property-location ModelCache.

    The cache is invalidated automatically when the roads-and-transport graph
    is newer than the cache file.

    Returns:
        A ``ModelCache`` storing lists of ``MapProperty`` objects keyed by tile.
    """
    return _get_road_and_transport_dependent_cache(
        list[rightmove.models.MapProperty],
        data_dir / "property_locations_cache.db",
        ttl=DEFAULT_PROPERTY_TILE_CACHE_RETENTION_TTL,
    )


@st.cache_resource
def get_journey_cache() -> ModelCache[int | None]:
    """Return the Streamlit-cached journey-duration ModelCache.

    The cache is invalidated automatically when the roads-and-transport graph
    is newer than the cache file.

    Returns:
        A ``ModelCache`` storing journey durations (minutes) or ``None``.
    """
    return _get_road_and_transport_dependent_cache(
        int | None,
        data_dir / "journey_cache.db",
        ttl=DEFAULT_JOURNEY_CACHE_TTL,
    )


def _get_road_and_transport_dependent_cache[T](
    t: Any, cache: Path, ttl: int = 86400
) -> ModelCache[T]:
    """Create a ModelCache that is invalidated when the roads-and-transport graph changes.

    If the cache file is older than the Dagster roads-and-transport asset it is
    deleted so that stale data is not served.

    Args:
        t: The type parameter used to construct the ``ModelCache``.
        cache: Path to the JSON cache file.

    Returns:
        A fresh or loaded ``ModelCache[T]``.
    """
    if cache.exists():
        graph_path = Path(".dagster/storage/roads_and_transport")
        if graph_path.exists() and cache.stat().st_mtime < graph_path.stat().st_mtime:
            cache.unlink()
    return ModelCache(t, cache, ttl=ttl)


# ==============================================================================
# QUERY MANAGEMENT
# ==============================================================================


def add_or_update_query(
    queries: list[CommuteDest],
    longitude: float,
    latitude: float,
    max_duration: int,
) -> list[CommuteDest]:
    """Add a new query or update the max duration of an existing one with the same coordinates.

    Args:
        queries: The current list of ``CommuteDest`` values.
        longitude: Longitude of the query destination.
        latitude: Latitude of the query destination.
        max_duration: Maximum acceptable commute duration in minutes.

    Returns:
        A new list with the query added or updated.
    """
    queries = queries.copy()
    query = CommuteDest(lon=longitude, lat=latitude, max_duration=max_duration)
    for i, existing in enumerate(queries):
        if (existing.lon, existing.lat) == (longitude, latitude):
            queries[i] = query
            return queries
    queries.append(query)
    return queries


# ==============================================================================
# ISOCHRONE DATA PROCESSING
# ==============================================================================


@st.cache_data(persist="disk")
def _process_isochrone_data(
    queries: Sequence[CommuteDest], offset: int
) -> tuple[list[Polygon], list[list[Polygon]]]:
    """Compute intersection and per-query isochrone polygons for a set of queries.

    Results are persisted to Streamlit's disk cache keyed by ``queries`` and
    ``offset``.

    Args:
        queries: Sequence of ``CommuteDest`` values defining commute destinations.
        offset: Station-cost penalty in minutes added to every station edge
            before computing isochrones.

    Returns:
        A tuple of ``(intersection_polys, isochrone_polys)`` where
        ``intersection_polys`` is a flat list of polygons covering the area
        reachable from *all* query locations, and ``isochrone_polys`` is a
        nested list (one inner list per query) of per-component polygons.
    """
    graph = load_graph(offset)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        separate_isochrones = list(
            executor.map(
                lookup,
                [graph] * len(queries),
                [q.lon for q in queries],
                [q.lat for q in queries],
                [q.max_duration for q in queries],
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


# ==============================================================================
# UI RENDERING SECTIONS
# ==============================================================================


def render_query_section() -> None:
    """Render the Streamlit section for entering and managing commute queries."""
    st.header("Flathunt!")
    longitude_value = st.text_input("Enter longitude:", key="longitude_input")
    latitude_value = st.text_input("Enter latitude:", key="latitude_input")
    max_duration = st.slider(
        "Maximum duration (in minutes):", min_value=1, max_value=120, value=30
    )

    if st.button("Add query", key="add_query_button"):
        try:
            longitude = float(longitude_value)
            latitude = float(latitude_value)
        except ValueError:
            st.error("Please enter valid numeric values for longitude and latitude.")
        else:
            queries = st.session_state.get("queries", [])
            queries = add_or_update_query(queries, longitude, latitude, max_duration)
            if queries:
                st.session_state["queries"] = queries
            else:
                st.session_state.pop("queries", None)

    if "queries" in st.session_state:
        st.status(
            f"Accepted query: {(longitude_value, latitude_value, max_duration)}",
            state="complete",
        )
        st.table(
            pd.DataFrame(
                st.session_state["queries"],
                columns=["Longitude", "Latitude", "Max Duration"],  # type: ignore
            )
        )
        st.button("Clear queries", on_click=lambda: st.session_state.pop("queries"))


def render_isochrone_section() -> None:
    """Render the Streamlit section for computing and displaying isochrones."""
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
    """Render the Streamlit section displaying the isochrone map."""
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
    """Render the Streamlit section for fetching and filtering properties by commute."""
    if "intersection_polys" not in st.session_state:
        return

    st.header("Search Properties in Intersection Area")
    last_channel = st.session_state.get("channel_selectbox", None)
    channel = st.selectbox("Select channel:", ["RENT", "BUY"], key="channel_selectbox")
    if channel != "RENT" and channel != "BUY":
        st.error("Invalid channel selected.")
        return
    if last_channel != channel:
        st.session_state.pop("properties", None)

    if st.button("Get property IDs in area", key="get_property_ids_button"):
        graph = load_graph(0)
        bounding_polygon = bounds_to_polygon((
            min(data["lon"] for data in graph.nodes.values()),
            min(data["lat"] for data in graph.nodes.values()),
            max(data["lon"] for data in graph.nodes.values()),
            max(data["lat"] for data in graph.nodes.values()),
        ))

        async def _collect_properties():
            all_props = []
            async for props in fetch_properties_within_optimal_regions(
                st.session_state["intersection_polys"],
                channel,
                bounding_polygon,
                get_property_ids_in_area_cache(),
            ):
                all_props.extend(props)
            seen: set[int] = set()
            result = []
            for p in all_props:
                if p.id not in seen:
                    seen.add(p.id)
                    result.append(p)
            return result

        property_locations = asyncio.run(_collect_properties())
        st.write(f"Found {len(property_locations)} unfiltered properties in the area.")
        queries = st.session_state["queries"]
        durations = asyncio.run(
            get_commute_durations(
                property_locations, queries, get_journey_cache(), tfl_api_key
            )
        )
        filtered = filter_by_commute(property_locations, durations, queries)
        st.write(
            f"Found {len(filtered)} properties in the area within commute criteria."
        )
        st.session_state["properties"] = [p for p, _ in filtered]


def render_results_section() -> None:
    """Render the Streamlit section for applying extra filters and displaying results."""
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
        render_property_table(filtered)


# ==============================================================================
# PROPERTY DISPLAY AND FORMATTING
# ==============================================================================


def render_property_table(
    properties: Iterable[tuple[rightmove.models.MapProperty, Sequence[int | None]]],
) -> None:
    """Render a Streamlit dataframe of properties with prices, sizes, URLs, and commute times.

    Args:
        properties: Iterable of ``(property, durations)`` pairs to display.
    """
    channel = st.session_state["channel_selectbox"]
    property_data = _convert_properties_to_dicts(properties, channel)
    st.dataframe(
        property_data,
        column_config={
            "URL": st.column_config.LinkColumn("URL"),
        },
        width="stretch",
    )


def _convert_properties_to_dicts(
    properties: Iterable[tuple[rightmove.models.MapProperty, Sequence[int | None]]],
    channel: Literal["RENT", "BUY"],
) -> list[dict[str, str | int | None]]:
    """Convert property/duration pairs into display-ready dicts for a Streamlit dataframe.

    Args:
        properties: Iterable of ``(property, durations)`` pairs.
        channel: Listing channel used to format the price field.

    Returns:
        A list of dicts with keys ``Name``, ``Price``, ``Size``, ``URL``,
        ``Minutes to Commute``, and one ``Commute to Query N`` key per query.

    Raises:
        ValueError: If ``channel`` is neither ``"RENT"`` nor ``"BUY"``.
    """
    property_data = []
    for property, prop_durations in properties:
        if property.property_url is None:
            continue
        if channel == "RENT":
            price = (
                rightmove.price.normalize(property.price) if property.price else "N/A"
            )
        elif channel == "BUY":
            price = property.price.amount if property.price else "N/A"
        else:
            raise ValueError("Invalid channel")
        commute_durations = {
            f"Commute to Query {i + 1}": (f"{d} mins" if d is not None else "N/A")
            for i, d in enumerate(prop_durations)
        }
        commute_values = [d for d in prop_durations if d is not None]
        property_data.append({
            "Name": property.display_address or "N/A",
            "Price": f"£{price:,}" if isinstance(price, int | float) else price,
            "Size": property.display_size or "N/A",
            "URL": rightmove.api.property_url(property.property_url),
            "Minutes to Commute": max(commute_values) if commute_values else "N/A",
            **commute_durations,
        })
    return property_data


# ==============================================================================
# MAP AND VISUALIZATION HELPERS
# ==============================================================================


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
    """Build GeoDataFrames for intersection and isochrone polygons, reprojected to WGS84.

    Args:
        polys: Intersection polygons in BNG (EPSG:27700).
        other_polys: Per-query tuples of isochrone polygons in BNG (EPSG:27700).

    Returns:
        A tuple of ``(all_polys_gdf, center_point_wgs84)`` where
        ``all_polys_gdf`` is a combined GeoDataFrame reprojected to WGS84 with
        a ``type`` column, and ``center_point_wgs84`` is a single-point
        GeoSeries at the centroid of all polygons.
    """
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
    queries: tuple[CommuteDest, ...],
    polys: tuple[Polygon, ...],
    isochrone_polys: tuple[tuple[Polygon | GeometryCollection, ...], ...],
):
    """Build a Plotly choropleth map of isochrone and intersection polygons.

    For a single query, only the intersection polygons are shown (the
    per-query isochrones are omitted as they would be identical).

    Args:
        queries: Tuple of ``CommuteDest`` values defining commute destinations.
        polys: Intersection polygons in BNG (EPSG:27700).
        isochrone_polys: Per-query tuples of isochrone polygons in BNG (EPSG:27700).

    Returns:
        A Plotly Figure containing the choropleth map.
    """
    # Make map
    other_polys = [] if len(queries) == 1 else isochrone_polys
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
    """Render a Plotly choropleth map figure from a combined GeoDataFrame.

    Intersection polygons are coloured red; each query's isochrone is assigned
    a distinct colour cycling through a fixed palette.

    Args:
        all_polys_gdf: A WGS84 GeoDataFrame with a ``type`` column whose values
            are ``"Intersection"`` or ``"Query N"``.
        center_lat: Latitude of the map centre in WGS84.
        center_lon: Longitude of the map centre in WGS84.
        num_other_polys: Number of distinct query isochrone types to colour.

    Returns:
        A Plotly Figure containing the choropleth map.
    """
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
