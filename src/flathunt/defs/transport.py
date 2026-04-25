import asyncio
import datetime
import itertools
import logging
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
from flathunt.defs.resources import TflResource
from flathunt.defs.sources import tfl_network_topology
from flathunt.geometry import wgs84_to_bng

logger = logging.getLogger(__name__)


class Config(dg.Config):
    allowed_modes: list[tfl.models.ModeId] = Field(
        default_factory=lambda: [
            tfl.models.ModeId.TUBE,
            tfl.models.ModeId.OVERGROUND,
            tfl.models.ModeId.DLR,
            tfl.models.ModeId.ELIZABETH_LINE,
            tfl.models.ModeId.WALKING,
        ]
    )


def _get_next_arrival_datetime(
    allowed_modes: list[tfl.models.ModeId],
) -> datetime.datetime:
    """Get the next 09:00 UTC datetime for journey planning."""
    return tfl.api.get_next_datetime(datetime.time(9, 0, 0, tzinfo=datetime.UTC))


async def _query_journey(
    tf_client: tfl.api.Tfl,
    line_id: str,
    stop_point: tfl.models.StopPointDetail,
    other_stop_point: tfl.models.StopPointDetail,
    arrival_datetime: datetime.datetime,
    allowed_modes: list[tfl.models.ModeId],
) -> tuple[str, str, str, float | None]:
    """Query TfL for journey duration between two stops on a line.

    Args:
        tf_client: TfL API client.
        line_id: The transit line identifier.
        stop_point: Origin stop point.
        other_stop_point: Destination stop point.
        arrival_datetime: Desired arrival time for planning.
        allowed_modes: Transit modes to consider.

    Returns:
        Tuple of (line_id, from_station_id, to_station_id, duration_or_none).
    """
    try:
        journey_results = await tf_client.get_journey_results(
            from_location=stop_point.id,
            to_location=other_stop_point.id,
            arrival_datetime=arrival_datetime,
            modes=allowed_modes,
            use_multi_modal_call=False,
        )
    except tfl.exceptions.JourneyNotFoundError:
        return line_id, stop_point.id, other_stop_point.id, None
    if not isinstance(journey_results, tfl.models.JourneyResults):
        return line_id, stop_point.id, other_stop_point.id, None
    min_duration = min(jr.duration for jr in journey_results.journeys)
    return line_id, stop_point.id, other_stop_point.id, min_duration


def _add_transport_nodes(
    graph: nx.Graph,
    line_id_stop_points: dict[str, list[tfl.models.StopPointDetail]],
) -> None:
    """Add all transit stop nodes to the graph."""
    for line_id in line_id_stop_points:
        for stop_point in line_id_stop_points[line_id]:
            if stop_point.lon is None or stop_point.lat is None:
                continue
            x, y = wgs84_to_bng(stop_point.lon, stop_point.lat)
            if (x, y) not in graph:
                graph.add_node(
                    (x, y),
                    x=x,
                    y=y,
                    lat=stop_point.lat,
                    lon=stop_point.lon,
                    station_name=stop_point.common_name,
                )


def _add_transport_edges(
    graph: nx.Graph,
    line_id_stop_points: dict[str, list[tfl.models.StopPointDetail]],
    all_station_durations: dict[str, dict[str, dict[str, float]]],
) -> list[tuple[str, str, str]]:
    """Add transit line edges to the graph and return list of missing pairs.

    Args:
        graph: NetworkX graph to modify.
        line_id_stop_points: Mapping of line IDs to their stop points.
        all_station_durations: Cached journey durations indexed by line, from, and to station.

    Returns:
        List of (line_id, from_id, to_id) tuples for missing duration pairs.
    """
    missing_pairs = []

    for line_id in line_id_stop_points:
        line_durations = all_station_durations.get(line_id, {})

        for stop_point, other_stop_point in itertools.combinations(
            line_id_stop_points[line_id], 2
        ):
            stop_id = stop_point.naptan_id
            other_id = other_stop_point.naptan_id

            if stop_point.lon is None or stop_point.lat is None:
                continue
            if other_stop_point.lon is None or other_stop_point.lat is None:
                continue
            x1, y1 = wgs84_to_bng(stop_point.lon, stop_point.lat)
            x2, y2 = wgs84_to_bng(other_stop_point.lon, other_stop_point.lat)

            duration = None
            if stop_id in line_durations and other_id in line_durations[stop_id]:
                duration = line_durations[stop_id][other_id]
            elif other_id in line_durations and stop_id in line_durations[other_id]:
                duration = line_durations[other_id][stop_id]

            if duration is None:
                missing_pairs.append((line_id, stop_id, other_id))
                continue

            graph.add_edge(
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

    return missing_pairs


@dg.asset(
    deps=[tfl_network_topology],
    automation_condition=dg.AutomationCondition.eager(),
    group_name="network_data",
)
async def transport(config: Config, tfl_resource: TflResource) -> nx.Graph:
    """Build a public transit network graph from TfL data.

    Fetches current TfL line and stop point information, queries journey times
    between all stop combinations on each line, and constructs a NetworkX graph
    with stations as nodes and transit connections as weighted edges.

    Args:
        config: Asset configuration with allowed transit modes.
        tfl_resource: TfL API resource providing the API key.

    Returns:
        A NetworkX Graph representing the TfL transit network with time-based
        edge weights and station metadata.
    """
    tf_client = tfl.api.Tfl(app_key=tfl_resource.api_key)
    lines = await tf_client.get_all_lines_routes()
    line_id_stop_points: dict[str, list[tfl.models.StopPointDetail]] = {}
    for line in tqdm.tqdm(lines):
        if line.mode_name not in config.allowed_modes:
            continue
        line_id_stop_points[line.id] = await tf_client.get_stop_points_by_line(line.id)

    arrival_datetime = _get_next_arrival_datetime(config.allowed_modes)
    queries = []
    for line_id, stop_points in line_id_stop_points.items():
        for stop_point, other_stop_point in itertools.combinations(stop_points, 2):
            queries.append((line_id, stop_point, other_stop_point))

    all_station_durations: dict[str, dict[str, dict[str, float]]] = {}
    awaitables = [
        _query_journey(
            tf_client,
            line_id,
            stop_point,
            other_stop_point,
            arrival_datetime,
            config.allowed_modes,
        )
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
    _add_transport_nodes(transport_graph, line_id_stop_points)
    missing_pairs = _add_transport_edges(
        transport_graph, line_id_stop_points, all_station_durations
    )

    logger.info("Missing pairs: %d", len(missing_pairs))
    if missing_pairs:
        line_counts = Counter(line_id for line_id, _, _ in missing_pairs)
        logger.info("Missing pairs by line:")
        for line_id, count in line_counts.most_common():
            logger.info("  %s: %d", line_id, count)
    return transport_graph
