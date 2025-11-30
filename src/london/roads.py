"""Road network graph construction and utilities."""

from concurrent.futures import ThreadPoolExecutor

import geopandas as gpd
import networkx as nx
from pyproj import Geod
from shapely.geometry import LineString
from tqdm import tqdm


class RoadGraphLoader:
    """
    A class for loading and managing road network graphs.
    """

    def __init__(self, directed: bool = True, num_workers: int | None = None):
        """
        Initialize the RoadGraphLoader.

        Args:
            directed: If True, create a directed graph, otherwise undirected
            num_workers: Number of threads to use for parallel processing.
                        If None, uses the number of CPUs.
        """
        self.directed = directed
        self.num_workers = num_workers
        self.geod = Geod(ellps="WGS84")
        self.graph: nx.Graph | nx.DiGraph | None = None

    def load_from_geodataframe(
        self, roads_gdf: gpd.GeoDataFrame
    ) -> nx.Graph | nx.DiGraph:
        """
        Build a NetworkX graph from a GeoDataFrame of road geometries.

        Args:
            roads_gdf: GeoDataFrame containing road geometries (LineString or MultiLineString)

        Returns:
            NetworkX graph with nodes at road endpoints/intersections and edges for road segments.
            Edge weights are geodesic distances in meters.
        """
        # Create graph
        self.graph = nx.DiGraph() if self.directed else nx.Graph()

        # Process roads in parallel using executor.map
        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            # Map roads to processing function with progress bar
            road_iterator = executor.map(
                self._extract_road_data, [road for _, road in roads_gdf.iterrows()]
            )

            # Collect all nodes and edges
            for nodes, edges in tqdm(
                road_iterator, total=len(roads_gdf), desc="Building graph"
            ):
                # Add nodes to graph
                for node_id, attrs in nodes:
                    if node_id not in self.graph:
                        self.graph.add_node(node_id, **attrs)

                # Add edges to graph
                for start_node, end_node, attrs in edges:
                    self.graph.add_edge(start_node, end_node, **attrs)

        return self.graph

    def _extract_road_data(
        self, road
    ) -> tuple[list[tuple[str, dict]], list[tuple[str, str, dict]]]:
        """
        Extract nodes and edges from a single road feature.

        Args:
            road: Road feature with geometry and attributes

        Returns:
            Tuple of (nodes, edges) where:
                - nodes is a list of (node_id, attributes) tuples
                - edges is a list of (start_node, end_node, attributes) tuples
        """
        nodes = []
        edges = []

        if road.geometry.geom_type == "LineString":
            road_nodes, road_edges = self._process_linestring_data(road, road.geometry)
            nodes.extend(road_nodes)
            edges.extend(road_edges)
        elif road.geometry.geom_type == "MultiLineString":
            for line in road.geometry.geoms:
                road_nodes, road_edges = self._process_linestring_data(road, line)
                nodes.extend(road_nodes)
                edges.extend(road_edges)

        return nodes, edges

    def _process_linestring_data(
        self, road, linestring: LineString
    ) -> tuple[list[tuple[str, dict]], list[tuple[str, str, dict]]]:
        """
        Process a single LineString geometry and extract nodes/edges data.

        Args:
            road: Road feature with attributes
            linestring: LineString geometry to process

        Returns:
            Tuple of (nodes, edges) where:
                - nodes is a list of (node_id, attributes) tuples
                - edges is a list of (start_node, end_node, attributes) tuples
        """
        coords = list(linestring.coords)
        nodes = []
        edges = []

        # Extract nodes
        for coord in coords:
            node_id = f"{coord[0]:.6f},{coord[1]:.6f}"
            attrs = {"pos": coord, "lon": coord[0], "lat": coord[1]}
            nodes.append((node_id, attrs))

        # Extract edges
        for i in range(len(coords) - 1):
            start_node = f"{coords[i][0]:.6f},{coords[i][1]:.6f}"
            end_node = f"{coords[i + 1][0]:.6f},{coords[i + 1][1]:.6f}"

            # Calculate geodesic distance in meters
            lon1, lat1 = coords[i][0], coords[i][1]
            lon2, lat2 = coords[i + 1][0], coords[i + 1][1]
            _, _, dist = self.geod.inv(lon1, lat1, lon2, lat2)

            # Create edge attributes
            attrs = {
                "weight": dist,
                "road_type": road.get("fclass", "unknown"),
                "name": road.get("name", ""),
                "maxspeed": road.get("maxspeed", None),
            }
            edges.append((start_node, end_node, attrs))

        return nodes, edges

    def load_from_shapefile(self, shapefile_path: str) -> nx.Graph | nx.DiGraph:
        """
        Load a roads shapefile and build a graph from it.

        Args:
            shapefile_path: Path to the shapefile

        Returns:
            NetworkX graph
        """
        roads_gdf = gpd.read_file(shapefile_path)
        return self.load_from_geodataframe(roads_gdf)


def build_road_graph(
    roads_gdf: gpd.GeoDataFrame, directed: bool = True, num_workers: int | None = None
) -> nx.Graph | nx.DiGraph:
    """
    Build a NetworkX graph from a GeoDataFrame of road geometries.

    Args:
        roads_gdf: GeoDataFrame containing road geometries (LineString or MultiLineString)
        directed: If True, create a directed graph, otherwise undirected
        num_workers: Number of threads to use for parallel processing.
                    If None, uses the number of CPUs.

    Returns:
        NetworkX graph with nodes at road endpoints/intersections and edges for road segments.
        Edge weights are geodesic distances in meters.
    """
    loader = RoadGraphLoader(directed=directed, num_workers=num_workers)
    return loader.load_from_geodataframe(roads_gdf)
