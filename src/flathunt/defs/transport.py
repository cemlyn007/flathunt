import asyncio
import datetime
import itertools
import os
from datetime import timezone

import dagster as dg
import geopandas as gpd
import networkx as nx
import numpy as np
import tqdm
import tqdm.asyncio
from pydantic import Field
from shapely.geometry import LineString, Point

import tfl.api
import tfl.exceptions
import tfl.models


class Config(dg.Config):
    tfl_api_key: str = Field(
        default_factory=lambda: os.environ["FLATHUNT__TFL_API_KEY"]
    )
    allowed_modes: list[tfl.models.ModeId] = Field(
        default_factory=lambda: [
            tfl.models.ModeId.TUBE,
            tfl.models.ModeId.OVERGROUND,
            tfl.models.ModeId.DLR,
            tfl.models.ModeId.ELIZABETH_LINE,
            tfl.models.ModeId.WALKING,
        ]
    )


def project_to_meters(lon: float, lat: float):
    point_wgs84 = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326")
    point_osgb36 = point_wgs84.to_crs("EPSG:27700")
    return point_osgb36.x.item(), point_osgb36.y.item()


def euclidean(x1, y1, x2, y2):
    return np.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


@dg.asset
async def transport(context: dg.AssetExecutionContext, config: Config) -> nx.Graph:
    tf_client = tfl.api.Tfl(app_key=config.tfl_api_key)
    lines = await tf_client.get_all_lines_routes()
    line_id_stop_points: dict[str, list[tfl.models.StopPointDetail]] = {}
    for line in tqdm.tqdm(lines):
        if line.mode_name not in config.allowed_modes:
            continue
        line_id_stop_points[line.id] = await tf_client.get_stop_points_by_line(line.id)

    arrival_datetime = tfl.api.get_next_datetime(
        datetime.time(9, 0, 0, tzinfo=timezone.utc)
    )
    queries = []
    for line_id, stop_points in line_id_stop_points.items():
        for stop_point, other_stop_point in itertools.combinations(stop_points, 2):
            queries.append((line_id, stop_point, other_stop_point))

    async def process_query_queue(line_id, stop_point, other_stop_point):
        try:
            journey_results = await tf_client.get_journey_results(
                from_location=stop_point.id,
                to_location=other_stop_point.id,
                arrival_datetime=arrival_datetime,
                modes=config.allowed_modes,
                use_multi_modal_call=False,
            )
        except tfl.exceptions.JourneyNotFoundError:
            return line_id, stop_point.id, other_stop_point.id, None
        if not isinstance(journey_results, tfl.models.JourneyResults):
            return line_id, stop_point.id, other_stop_point.id, None
        min_duration = min(jr.duration for jr in journey_results.journeys)
        return line_id, stop_point.id, other_stop_point.id, min_duration

    all_station_durations: dict[str, dict[str, dict[str, float]]] = {}
    awaitables = [
        process_query_queue(line_id, stop_point, other_stop_point)
        for line_id, stop_point, other_stop_point in queries
        if (
            all_station_durations.get(line_id, {})
            .get(stop_point.id, {})
            .get(other_stop_point.id)
            is None
        )
    ]

    for future in tqdm.asyncio.tqdm(
        asyncio.as_completed(awaitables), total=len(awaitables)
    ):
        line_id, from_station_id, to_station_id, min_duration = await future
        if min_duration is not None:
            all_station_durations.setdefault(line_id, {}).setdefault(
                from_station_id, {}
            )[to_station_id] = min_duration

    transport_graph = nx.Graph()
    missing_pairs = []

    for line_id in line_id_stop_points.keys():
        for stop_point in line_id_stop_points[line_id]:
            x, y = project_to_meters(stop_point.lon, stop_point.lat)
            if (x, y) not in transport_graph:
                transport_graph.add_node(
                    (x, y),
                    x=x,
                    y=y,
                    station_name=stop_point.common_name,
                )

        line_durations = all_station_durations.get(line_id, {})

        for stop_point, other_stop_point in itertools.combinations(
            line_id_stop_points[line_id], 2
        ):
            # Use naptan_id to match the keys in all_station_durations (from departure_stop_id)
            stop_id = stop_point.naptan_id
            other_id = other_stop_point.naptan_id

            x1, y1 = project_to_meters(stop_point.lon, stop_point.lat)
            x2, y2 = project_to_meters(other_stop_point.lon, other_stop_point.lat)

            # Try both directions since station_intervals only go one way
            duration = None
            if stop_id in line_durations and other_id in line_durations[stop_id]:
                duration = line_durations[stop_id][other_id]
            elif other_id in line_durations and stop_id in line_durations[other_id]:
                duration = line_durations[other_id][stop_id]

            if duration is None:
                missing_pairs.append((line_id, stop_id, other_id))
                continue

            duration += 5  # add 5 minutes for boarding/alighting

            transport_graph.add_edge(
                (x1, y1),
                (x2, y2),
                duration=duration,
                geometry=LineString(
                    [
                        (x1, y1),
                        (x2, y2),
                    ]
                ),
            )

    print(f"Missing pairs: {len(missing_pairs)}")
    if missing_pairs:
        # Show a sample of missing pairs by line
        from collections import Counter

        line_counts = Counter(line_id for line_id, _, _ in missing_pairs)
        print("Missing pairs by line:")
        for line_id, count in line_counts.most_common():
            print(f"  {line_id}: {count}")
    return transport_graph
