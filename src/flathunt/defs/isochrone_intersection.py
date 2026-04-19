import concurrent.futures
import logging
from typing import cast

import dagster as dg
import networkx as nx
from shapely.geometry.polygon import Polygon

from flathunt.defs.config import CommuteDestConfig
from flathunt.isochrone import (
    EDGE_BUFFER,
    NODE_BUFFER,
    get_intersection,
    lookup,
    make_poly,
)

logger = logging.getLogger(__name__)


class Config(dg.Config):
    queries: list[CommuteDestConfig]
    station_cost_offset: float = 0.0


@dg.asset
def isochrone_intersection(
    config: Config,
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
    if not config.queries:
        logger.warning("No commute queries configured; returning empty intersection.")
        return []

    graph = roads_and_transport.copy()
    if config.station_cost_offset != 0.0:
        for n_fr, n_to in graph.edges():
            if (
                "station_name" in graph.nodes[n_fr]
                or "station_name" in graph.nodes[n_to]
            ):
                graph.edges[n_fr, n_to]["duration"] += config.station_cost_offset

    logger.info("Computing isochrones for %d queries.", len(config.queries))
    isochrone_subgraphs = [
        lookup(graph, q.lon, q.lat, q.max_duration) for q in config.queries
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
    return non_empty
