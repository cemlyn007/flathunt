import asyncio
import datetime
import itertools
import logging
import os
from collections.abc import Collection
from typing import Literal

import geopandas as gpd
import networkx as nx
import tqdm
import tqdm.asyncio
from shapely.geometry import Point, box
from shapely.geometry.polygon import Polygon

import rightmove.api
import rightmove.models
import tfl.api
import tfl.models
from flathunt.isochrone import find_min_simplify_tolerance

logger = logging.getLogger(__name__)

TARGET_DATETIME = tfl.api.get_next_datetime(
    datetime.time(9, 0, 0, tzinfo=datetime.timezone.utc)
)
MAX_RIGHTMOVE_POLYLINE_POINTS = 1000
MAX_RIGHTMOVE_SEARCH_PROPERTIES = 499
MAX_RIGHTMOVE_GET_PROPERTIES = 25


def split_polygon(polygon: Polygon) -> list[Polygon]:
    minx, miny, maxx, maxy = polygon.bounds
    midx = (minx + maxx) / 2
    midy = (miny + maxy) / 2

    # Create 4 boxes
    boxes = [
        box(minx, miny, midx, midy),
        box(midx, miny, maxx, midy),
        box(minx, midy, midx, maxy),
        box(midx, midy, maxx, maxy),
    ]

    parts = []
    for b in boxes:
        intersection = polygon.intersection(b)
        if intersection.is_empty:
            continue

        if intersection.geom_type == "Polygon":
            parts.append(intersection)
        elif intersection.geom_type == "MultiPolygon":
            parts.extend(intersection.geoms)
        elif intersection.geom_type == "GeometryCollection":
            for geom in intersection.geoms:
                if geom.geom_type == "Polygon":
                    parts.append(geom)
                elif geom.geom_type == "MultiPolygon":
                    parts.extend(geom.geoms)
    return parts


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

    async def recursive_map_search(
        coords: list[tuple[float, float]], depth=0
    ) -> set[int]:
        if depth > 5:  # Safety break
            logger.warning("Max recursion depth reached for polygon subdivision.")
            # Fallback to just getting what we can
            search_results, _ = await rightmove_client.map_search(
                rightmove.api.SearchQuery(
                    location_identifier=rightmove.api.polyline_identifier(coords),
                    is_fetching=True,
                    view_type="MAP",
                    channel=channel,
                )
            )
            return {p.id for p in search_results}

        # Ensure coords limit
        if len(coords) > MAX_RIGHTMOVE_POLYLINE_POINTS:
            shapely_coords = [(lon, lat) for lat, lon in coords]
            poly = Polygon(shapely_coords)
            exterior, _ = find_min_simplify_tolerance(
                poly, max_coords=MAX_RIGHTMOVE_POLYLINE_POINTS
            )
            coords = [(y, x) for x, y in exterior.coords]

        search_results, count = await rightmove_client.map_search(
            rightmove.api.SearchQuery(
                location_identifier=rightmove.api.polyline_identifier(coords),
                is_fetching=True,
                view_type="MAP",
                channel=channel,
            )
        )

        if count > MAX_RIGHTMOVE_SEARCH_PROPERTIES:
            logger.info(
                f"Count {count} > {MAX_RIGHTMOVE_SEARCH_PROPERTIES}, subdividing (depth {depth})."
            )
            shapely_coords = [(lon, lat) for lat, lon in coords]
            poly = Polygon(shapely_coords)
            if not poly.is_valid:
                poly = poly.buffer(0)

            sub_polys = split_polygon(poly)

            results = set()
            for sub_poly in sub_polys:
                exterior, _ = find_min_simplify_tolerance(
                    sub_poly, max_coords=MAX_RIGHTMOVE_POLYLINE_POINTS
                )
                sub_coords = [(y, x) for x, y in exterior.coords]
                results.update(await recursive_map_search(sub_coords, depth=depth + 1))
            return results

        return {p.id for p in search_results}

    all_property_ids = set()
    for coord, coords in tqdm.tqdm(zip(min_times, best_coords), total=len(best_coords)):
        ids = await recursive_map_search(coords)
        all_property_ids.update(ids)
    return all_property_ids


async def get_properties(
    property_ids: Collection[int],
    channel: Literal["RENT", "BUY"] = "RENT",
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
