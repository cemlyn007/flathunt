import geopandas as gpd
from shapely import Point, Polygon

from flathunt.coords import LatLon

WGS84 = "EPSG:4326"
BNG = "EPSG:27700"


def wgs84_to_bng(lon: float, lat: float) -> tuple[float, float]:
    """Convert a WGS84 longitude/latitude point to British National Grid eastings/northings.

    Args:
        lon: Longitude in WGS84 (EPSG:4326).
        lat: Latitude in WGS84 (EPSG:4326).

    Returns:
        A tuple of (easting, northing) in BNG (EPSG:27700), in metres.
    """
    point_wgs84 = gpd.GeoSeries([Point(lon, lat)], crs=WGS84)
    point_bng = point_wgs84.to_crs(BNG)
    return point_bng.x.item(), point_bng.y.item()


def poly_bng_to_wgs84_coords(poly: Polygon) -> list[LatLon]:
    """Convert the exterior ring of a BNG polygon to a list of WGS84 coordinates.

    Args:
        poly: A Shapely Polygon whose coordinates are in BNG (EPSG:27700).

    Returns:
        A list of ``LatLon`` coordinates in WGS84 (EPSG:4326).
    """
    xs, ys = poly.exterior.coords.xy
    points_wgs84 = gpd.GeoSeries(
        [Point(x, y) for x, y in zip(xs, ys, strict=True)], crs=BNG
    ).to_crs(WGS84)
    return [LatLon(lat=p.y, lon=p.x) for p in points_wgs84]  # pyright: ignore[reportAttributeAccessIssue]


def poly_bng_to_wgs84(poly: Polygon) -> Polygon:
    """Reproject a BNG polygon to WGS84.

    Args:
        poly: A Shapely Polygon whose coordinates are in BNG (EPSG:27700).

    Returns:
        The reprojected Polygon in WGS84 (EPSG:4326).

    Raises:
        ValueError: If reprojection yields a number of geometries other than one.
    """
    converted = gpd.GeoSeries([poly], crs=BNG).to_crs(WGS84)
    if len(converted) != 1:
        raise ValueError(
            f"Expected 1 geometry after reprojection, got {len(converted)}"
        )
    return converted.iloc[0]  # pyright: ignore[reportReturnType]
