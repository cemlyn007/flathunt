import itertools
import os

import dagster as dg
import geopandas as gpd
import networkx as nx
import numpy as np
import tqdm
from shapely.geometry import LineString, Point


class Config(dg.Config):
    file_path: str = os.getenv(
        "FLATHUNT_ROADS_FILE_PATH",
        "greater-london-251126-free/gis_osm_roads_free_1.shp",
    )
    meters_per_minute: float = 60


def project_to_meters(lon: float, lat: float):
    point_wgs84 = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326")
    point_osgb36 = point_wgs84.to_crs("EPSG:27700")
    return point_osgb36.x.item(), point_osgb36.y.item()


def euclidean(x1, y1, x2, y2):
    return np.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def create_roads_graph(
    roads_gdf: gpd.GeoDataFrame, meters_per_minute: float
) -> nx.Graph:
    graph = nx.Graph()
    for _, road in tqdm.tqdm(roads_gdf.iterrows(), total=len(roads_gdf)):
        for (x1, y1), (x2, y2) in itertools.pairwise(road.geometry.coords):
            if (x1, y1) not in graph:
                graph.add_node((x1, y1), x=x1, y=y1)
            if (x2, y2) not in graph:
                graph.add_node((x2, y2), x=x2, y=y2)
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


@dg.asset
def roads(context: dg.AssetExecutionContext, config: Config) -> nx.Graph:
    roads_gdf = gpd.read_file(config.file_path)
    roads_gdf = roads_gdf.to_crs("EPSG:27700")
    graph = create_roads_graph(roads_gdf, config.meters_per_minute)
    return graph
