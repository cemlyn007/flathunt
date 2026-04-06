import operator

import geopandas as gpd
from shapely import Point, Polygon

WGS84 = "EPSG:4326"
BNG = "EPSG:27700"


def wgs84_to_bng(lon: float, lat: float) -> tuple[float, float]:
    point_wgs84 = gpd.GeoSeries([Point(lon, lat)], crs=WGS84)
    point_bng = point_wgs84.to_crs(BNG)
    return point_bng.x.item(), point_bng.y.item()


def poly_bng_to_wgs84_coords(poly: Polygon) -> list[tuple[float, float]]:
    xs, ys = poly.exterior.coords.xy
    points_wgs84 = gpd.GeoSeries(
        [Point(x, y) for x, y in zip(xs, ys, strict=True)], crs=BNG
    ).to_crs(WGS84)
    return list(map(operator.attrgetter("x", "y"), points_wgs84))


def poly_bng_to_wgs84(poly: Polygon) -> Polygon:
    converted = gpd.GeoSeries([poly], crs=BNG).to_crs(WGS84)
    if len(converted) != 1:
        raise ValueError(
            f"Expected 1 geometry after reprojection, got {len(converted)}"
        )
    return converted.iloc[0]  # pyright: ignore[reportReturnType]
