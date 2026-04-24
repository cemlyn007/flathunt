import asyncio
import datetime
import itertools
import logging
import os
from collections import Counter

import dagster as dg
import networkx as nx
import tqdm
import tqdm.asyncio
from pydantic import Field
from shapely.geometry import LineString

import tfl.api
import tfl.exceptions
import tfl.models
from flathunt.defs.sources import tfl_network_topology
from flathunt.geometry import wgs84_to_bng

logger = logging.getLogger(__name__)


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


@dg.asset(
    deps=[tfl_network_topology],
    automation_condition=dg.AutomationCondition.eager(),
)
async def transport(config: Config) -> nx.Graph:
    tf_client = tfl.api.Tfl(app_key=config.tfl_api_key)
    lines = await tf_client.get_all_lines_routes()
    line_id_stop_points: dict[str, list[tfl.models.StopPointDetail]] = {}
    for line in tqdm.tqdm(lines):
        if line.mode_name not in config.allowed_modes:
            continue
        line_id_stop_points[line.id] = await tf_client.get_stop_points_by_line(line.id)

    arrival_datetimes = tfl.api.get_next_weekday_datetimes(
        datetime.time(9, 0, 0, tzinfo=datetime.UTC), 5
    )
    queries = []
    for line_id, stop_points in line_id_stop_points.items():
        for stop_point, other_stop_point in itertools.combinations(stop_points, 2):
            queries.append((line_id, stop_point, other_stop_point))

    async def process_query_queue(line_id, stop_point, other_stop_point):
        min_duration = None
        try:
            for arrival_datetime in arrival_datetimes:
                try:
                    journey_results = await tf_client.get_journey_results(
                        from_location=stop_point.id,
                        to_location=other_stop_point.id,
                        arrival_datetime=arrival_datetime,
                        modes=config.allowed_modes,
                        use_multi_modal_call=False,
                    )
                except tfl.exceptions.JourneyNotFoundError:
                    continue
                if not isinstance(journey_results, tfl.models.JourneyResults):
                    continue
                day_min_duration = min(jr.duration for jr in journey_results.journeys)
                min_duration = (
                    day_min_duration
                    if min_duration is None
                    else min(min_duration, day_min_duration)
                )
        except tfl.exceptions.JourneyNotFoundError:
            return line_id, stop_point.id, other_stop_point.id, None
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

    for line_id in line_id_stop_points:
        for stop_point in line_id_stop_points[line_id]:
            if stop_point.lon is None or stop_point.lat is None:
                continue
            x, y = wgs84_to_bng(stop_point.lon, stop_point.lat)
            if (x, y) not in transport_graph:
                transport_graph.add_node(
                    (x, y),
                    x=x,
                    y=y,
                    lat=stop_point.lat,
                    lon=stop_point.lon,
                    station_name=stop_point.common_name,
                )

        line_durations = all_station_durations.get(line_id, {})

        for stop_point, other_stop_point in itertools.combinations(
            line_id_stop_points[line_id], 2
        ):
            # Use naptan_id to match the keys in all_station_durations (from departure_stop_id)
            stop_id = stop_point.naptan_id
            other_id = other_stop_point.naptan_id

            if stop_point.lon is None or stop_point.lat is None:
                continue
            if other_stop_point.lon is None or other_stop_point.lat is None:
                continue
            x1, y1 = wgs84_to_bng(stop_point.lon, stop_point.lat)
            x2, y2 = wgs84_to_bng(other_stop_point.lon, other_stop_point.lat)

            # Try both directions since station_intervals only go one way
            duration = None
            if stop_id in line_durations and other_id in line_durations[stop_id]:
                duration = line_durations[stop_id][other_id]
            elif other_id in line_durations and stop_id in line_durations[other_id]:
                duration = line_durations[other_id][stop_id]

            if duration is None:
                missing_pairs.append((line_id, stop_id, other_id))
                continue

            transport_graph.add_edge(
                (x1, y1),
                (x2, y2),
                duration=duration,
                geometry=LineString([
                    (x1, y1),
                    (x2, y2),
                ]),
            )

    logger.info("Missing pairs: %d", len(missing_pairs))
    if missing_pairs:
        line_counts = Counter(line_id for line_id, _, _ in missing_pairs)
        logger.info("Missing pairs by line:")
        for line_id, count in line_counts.most_common():
            logger.info("  %s: %d", line_id, count)
    return transport_graph
