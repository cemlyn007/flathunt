import itertools
import os

import dagster as dg
import geopandas as gpd
import networkx as nx
import tqdm
from shapely.geometry import LineString

from flathunt.defs.sources import roads_shapefile
from flathunt.geometry import euclidean, wgs84_to_bng


class Config(dg.Config):
    file_path: str = os.getenv(
        "FLATHUNT_ROADS_FILE_PATH",
        "greater-london-251126-free/gis_osm_roads_free_1.shp",
    )
    meters_per_minute: float = 60


def create_roads_graph(
    roads_gdf: gpd.GeoDataFrame, meters_per_minute: float
) -> nx.Graph:
    """Build a NetworkX graph from road geometries with time-based edge weights.

    Args:
        roads_gdf: GeoDataFrame of road geometries with LineString coordinates.
        meters_per_minute: Conversion factor to compute traversal duration.

    Returns:
        A NetworkX Graph with nodes for road endpoints and edges with length and duration.
    """
    graph = nx.Graph()
    for _, road in tqdm.tqdm(roads_gdf.iterrows(), total=len(roads_gdf)):
        for (lon1, lat1), (lon2, lat2) in itertools.pairwise(road.geometry.coords):
            x1, y1 = wgs84_to_bng(lon1, lat1)
            x2, y2 = wgs84_to_bng(lon2, lat2)
            if (x1, y1) not in graph:
                graph.add_node((x1, y1), x=x1, y=y1, lat=lat1, lon=lon1)
            if (x2, y2) not in graph:
                graph.add_node((x2, y2), x=x2, y=y2, lat=lat2, lon=lon2)
            if not graph.has_edge((x1, y1), (x2, y2)):
                length = euclidean(x1, y1, x2, y2).item()
                graph.add_edge(
                    (x1, y1),
                    (x2, y2),
                    length=length,
                    duration=length / meters_per_minute,
                    geometry=LineString([(x1, y1), (x2, y2)]),
                )  # in meters
    return graph


@dg.asset(
    deps=[roads_shapefile],
    automation_condition=dg.AutomationCondition.eager(),
    group_name="network_data",
)
def roads(context: dg.AssetExecutionContext, config: Config) -> nx.Graph:
    roads_gdf = gpd.read_file(config.file_path)
    graph = create_roads_graph(roads_gdf, config.meters_per_minute)
    return graph
