import concurrent.futures
import logging
from typing import cast

import dagster as dg
import networkx as nx
from shapely.geometry.polygon import Polygon

from flathunt.defs.resources import QueriesResource
from flathunt.isochrone import (
    EDGE_BUFFER,
    NODE_BUFFER,
    get_intersection,
    lookup,
    make_poly,
)

logger = logging.getLogger(__name__)


class Config(dg.Config):
    station_cost_offset: float = 0.0


def _apply_station_cost_offset(graph: nx.Graph, station_cost_offset: float) -> nx.Graph:
    """Apply a cost offset to edges connected to station nodes."""
    if station_cost_offset == 0.0:
        return graph

    graph_copy = graph.copy()
    for n_fr, n_to in graph_copy.edges():
        if (
            "station_name" in graph_copy.nodes[n_fr]
            or "station_name" in graph_copy.nodes[n_to]
        ):
            graph_copy.edges[n_fr, n_to]["duration"] += station_cost_offset
    return graph_copy


@dg.asset(group_name="network_data", io_manager_key="fs_io_manager")
def isochrone_intersection(
    context: dg.AssetExecutionContext,
    config: Config,
    queries: QueriesResource,
    roads_and_transport: nx.Graph,
) -> list[Polygon]:
    """Compute the isochrone intersection polygons for a set of commute destinations.

    For each query destination the reachable area within its ``max_duration``
    is computed as a set of subgraphs.  Those sets are then intersected to find
    the region that is reachable from *every* destination within its respective
    time limit.  The resulting connected components are converted to Shapely
    Polygons in British National Grid (EPSG:27700).

    Args:
        config: Asset configuration containing commute destinations and an
            optional station penalty.
        roads_and_transport: The merged road + transit NetworkX graph produced
            by the ``roads_and_transport`` asset.

    Returns:
        A list of non-empty BNG Polygons representing the intersection area.
        Returns an empty list when no intersection exists.
    """
    if not queries.queries:
        logger.warning("No commute queries configured; returning empty intersection.")
        return []

    graph = _apply_station_cost_offset(roads_and_transport, config.station_cost_offset)

    logger.info("Computing isochrones for %d queries.", len(queries.queries))
    isochrone_subgraphs = [
        lookup(graph, q.lon, q.lat, q.max_duration) for q in queries.queries
    ]

    logger.info("Computing intersection of isochrone subgraphs.")
    intersection_subgraphs = get_intersection(graph, isochrone_subgraphs)

    if not intersection_subgraphs:
        logger.warning("Isochrone intersection is empty.")
        return []

    logger.info(
        "Building polygons from %d intersection subgraph(s).",
        len(intersection_subgraphs),
    )
    with concurrent.futures.ThreadPoolExecutor() as executor:
        polys = list(
            executor.map(
                lambda sg: make_poly(sg, EDGE_BUFFER, NODE_BUFFER),
                intersection_subgraphs,
            )
        )

    non_empty = cast(list[Polygon], [p for p in polys if not p.is_empty])
    logger.info("Produced %d non-empty intersection polygon(s).", len(non_empty))
    context.add_output_metadata({"polygon_count": len(non_empty)})
    return non_empty
