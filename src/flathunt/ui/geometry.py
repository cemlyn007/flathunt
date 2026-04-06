import operator

import geopandas as gpd
from shapely import Point, Polygon


def poly_bng_to_wgs84_coords(poly: Polygon) -> list[tuple[float, float]]:
    xs, ys = poly.exterior.coords.xy
    points_wgs84 = gpd.GeoSeries(
        [Point(x, y) for x, y in zip(xs, ys, strict=True)], crs="EPSG:27700"
    ).to_crs("EPSG:4326")
    return list(map(operator.attrgetter("x", "y"), points_wgs84))


def poly_bng_to_wgs84(poly: Polygon) -> Polygon:
    converted = gpd.GeoSeries([poly], crs="EPSG:27700").to_crs("EPSG:4326")
    if len(converted) != 1:
        raise ValueError(
            f"Expected 1 geometry after reprojection, got {len(converted)}"
        )
    return converted.iloc[0]  # pyright: ignore[reportReturnType]
