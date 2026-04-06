import datetime
import logging
from typing import Literal

from shapely.geometry import box
from shapely.geometry.polygon import Polygon

import rightmove.api
import rightmove.models
import tfl.api
import tfl.models
from flathunt.ui.isochrone import find_min_simplify_tolerance

logger = logging.getLogger(__name__)

TARGET_DATETIME = tfl.api.get_next_datetime(
    datetime.time(9, 0, 0, tzinfo=datetime.timezone.utc)
)
MAX_RIGHTMOVE_POLYLINE_POINTS = 1000
MAX_RIGHTMOVE_SEARCH_PROPERTIES = 499


def split_polygon(polygon: Polygon) -> list[Polygon]:
    minx, miny, maxx, maxy = polygon.bounds
    midx = (minx + maxx) / 2
    midy = (miny + maxy) / 2

    # Create 4 boxes
    boxes = [
        box(minx, miny, midx, midy),
        box(midx, miny, maxx, midy),
        box(minx, midy, midx, maxy),
        box(midx, midy, maxx, maxy),
    ]

    parts = []
    for b in boxes:
        intersection = polygon.intersection(b)
        if intersection.is_empty:
            continue

        if intersection.geom_type == "Polygon":
            parts.append(intersection)
        elif intersection.geom_type == "MultiPolygon":
            if not hasattr(intersection, "geoms"):
                raise ValueError(
                    f"Expected MultiPolygon to have 'geoms' attribute, got {type(intersection)}"
                )
            parts.extend(getattr(intersection, "geoms"))
        elif intersection.geom_type == "GeometryCollection":
            if not hasattr(intersection, "geoms"):
                raise ValueError(
                    f"Expected MultiPolygon to have 'geoms' attribute, got {type(intersection)}"
                )
            for geom in getattr(intersection, "geoms"):
                if geom.geom_type == "Polygon":
                    parts.append(geom)
                elif geom.geom_type == "MultiPolygon":
                    parts.extend(geom.geoms)
    return parts


async def fetch_journey_results(
    client: tfl.api.Tfl, lon: float, lat: float, query_lon: float, query_lat: float
) -> float | None:
    try:
        journey_results = await client.get_journey_results(
            from_location=(lat, lon),
            to_location=(query_lat, query_lon),
            arrival_datetime=TARGET_DATETIME,
            modes=[
                tfl.models.ModeId.TUBE,
                tfl.models.ModeId.OVERGROUND,
                tfl.models.ModeId.DLR,
                tfl.models.ModeId.ELIZABETH_LINE,
                tfl.models.ModeId.WALKING,
            ],
            use_multi_modal_call=False,
        )
        if isinstance(journey_results, tfl.models.DisambiguationResult):
            logger.error(
                "Disambiguation result for journey from (%s, %s) to (%s, %s)",
                lon,
                lat,
                query_lon,
                query_lat,
            )
            return None
        min_time = min(journey.duration for journey in journey_results.journeys)
        return min_time
    except Exception:
        logger.exception(
            "Exception fetching journey from (%s, %s) to (%s, %s)",
            lon,
            lat,
            query_lon,
            query_lat,
        )
        return None


def _subdivide_exterior(
    coords: list[tuple[float, float]],
) -> list[list[tuple[float, float]]]:
    shapely_coords = [(lon, lat) for lat, lon in coords]
    poly = Polygon(shapely_coords)
    if not poly.is_valid:
        poly = poly.buffer(0)

    polys = split_polygon(poly)
    results = []
    for sub_poly in polys:
        if sub_poly.is_empty or not sub_poly.is_valid or sub_poly.area < 1e-9:
            continue

        if len(sub_poly.exterior.coords) <= MAX_RIGHTMOVE_POLYLINE_POINTS:
            exterior = sub_poly.exterior
        else:
            exterior, _ = find_min_simplify_tolerance(
                sub_poly, max_coords=MAX_RIGHTMOVE_POLYLINE_POINTS
            )
        # Check if simplified polygon is valid
        if Polygon(exterior).area < 1e-9:
            continue

        results.append([(y, x) for x, y in exterior.coords])

    return results


async def get_property_ids_in_area(
    coords: list[tuple[float, float]], channel: Literal["RENT", "BUY"] = "RENT", depth=0
) -> list[rightmove.models.MapProperty]:
    rightmove_client = rightmove.api.Rightmove()
    # Ensure coords limit
    if len(coords) > MAX_RIGHTMOVE_POLYLINE_POINTS:
        coords_list = _subdivide_exterior(coords)
        results = []
        for sub_coords in coords_list:
            results.extend(
                property_location
                for property_location in await get_property_ids_in_area(
                    sub_coords, channel=channel, depth=depth + 1
                )
                if not any(result.id == property_location.id for result in results)
            )
        return results
    else:
        search_results, count = await rightmove_client.map_search(
            rightmove.api.SearchQuery(
                location_identifier=rightmove.api.polyline_identifier(coords),
                is_fetching=True,
                channel=channel,
            )
        )
        if count > MAX_RIGHTMOVE_SEARCH_PROPERTIES:
            logger.info(
                f"Count {count} > {MAX_RIGHTMOVE_SEARCH_PROPERTIES}, subdividing (depth {depth})."
            )
            coords_list = _subdivide_exterior(coords)
            results = []
            for sub_coords in coords_list:
                results.extend(
                    property_location
                    for property_location in await get_property_ids_in_area(
                        sub_coords, channel=channel, depth=depth + 1
                    )
                    if not any(result.id == property_location.id for result in results)
                )
            return results
        else:
            return search_results


def check_property_size(
    property: rightmove.models.MapProperty, min_square_meters: float
):
    if property.display_size:
        if property.display_size.endswith(" sq. ft."):
            square_ft = int(
                property.display_size.removesuffix(" sq. ft.").replace(",", "")
            )
            square_meters = int(square_ft * 0.092903)
            if square_meters < min_square_meters:
                return False
        elif property.display_size.endswith(" sqm"):
            square_meters = int(
                property.display_size.removesuffix(" sqm").replace(",", "")
            )
            if square_meters < min_square_meters:
                return False
    return True
