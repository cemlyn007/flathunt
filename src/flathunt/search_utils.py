import asyncio
import datetime
import logging
from collections.abc import Callable
from typing import Literal

from shapely.geometry import GeometryCollection, MultiPolygon, box
from shapely.geometry.polygon import LinearRing, Polygon

import rightmove.api
import rightmove.models
import tfl.api
import tfl.models
from flathunt.coords import LatLon
from flathunt.isochrone import find_min_simplify_tolerance
from rightmove.floor_plan import _SQFT_TO_SQM

logger = logging.getLogger(__name__)

TARGET_DATETIME = tfl.api.get_next_datetime(datetime.time(9, 0, 0, tzinfo=datetime.UTC))
MAX_RIGHTMOVE_POLYLINE_POINTS = 1000


# ============================================================================
# Utility Functions
# ============================================================================


def check_property_size(
    property: rightmove.models.MapProperty, min_square_meters: float
):
    """Check whether a property meets a minimum floor-area requirement.

    Parses the ``display_size`` field, which may be expressed in square feet
    or square metres. Properties with no size information are considered to
    pass the check.

    Args:
        property: The Rightmove property to check.
        min_square_meters: Minimum acceptable floor area in square metres.

    Returns:
        ``True`` if the property's size is unknown or at least ``min_square_meters``,
        ``False`` if it is known and below the threshold.
    """
    if property.display_size:
        if property.display_size.endswith(" sq. ft."):
            square_ft = int(
                property.display_size.removesuffix(" sq. ft.").replace(",", "")
            )
            square_meters = int(square_ft * _SQFT_TO_SQM)
            if square_meters < min_square_meters:
                return False
        elif property.display_size.endswith(" sqm"):
            square_meters = int(
                property.display_size.removesuffix(" sqm").replace(",", "")
            )
            if square_meters < min_square_meters:
                return False
    return True


def split_polygon(polygon: Polygon) -> list[Polygon]:
    """Split a polygon into up to four quadrant sub-polygons by bisecting its bounding box.

    Args:
        polygon: The Shapely Polygon to split.

    Returns:
        A list of Polygon parts. Empty or degenerate intersections are omitted.
    """
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

        if isinstance(intersection, Polygon):
            parts.append(intersection)
        elif isinstance(intersection, MultiPolygon):
            parts.extend(intersection.geoms)
        elif isinstance(intersection, GeometryCollection):
            for geom in intersection.geoms:
                if isinstance(geom, Polygon):
                    parts.append(geom)
                elif isinstance(geom, MultiPolygon):
                    parts.extend(geom.geoms)
                else:
                    # Degenerate geometries (Point, LineString) not useful for subdivision
                    logger.warning(
                        "Skipping geometry type %s within collection from polygon intersection",
                        type(geom).__name__,
                    )
        else:
            # Degenerate intersections (Point, LineString) not useful for subdivision
            logger.warning(
                "Skipping geometry type %s from polygon intersection",
                type(intersection).__name__,
            )
    return parts


# ============================================================================
# Private Helper Functions
# ============================================================================


def _subdivide_exterior(
    exterior: LinearRing,
) -> list[LinearRing]:
    """Subdivide a polygon exterior into parts that each satisfy the Rightmove coordinate limit.

    The polygon is split into quadrants recursively until every part has at
    most ``MAX_RIGHTMOVE_POLYLINE_POINTS`` vertices (after optional simplification).

    Args:
        exterior: Exterior ring of the polygon in WGS84.

    Returns:
        A list of exterior rings, safe to pass directly to the Rightmove
        polyline search endpoint.
    """
    poly = Polygon(exterior)
    if not poly.is_valid:
        poly = poly.buffer(0)

    polys = split_polygon(poly)
    results = []
    for sub_poly in polys:
        if sub_poly.is_empty or not sub_poly.is_valid or sub_poly.area < 1e-9:
            continue

        if len(sub_poly.exterior.coords) <= MAX_RIGHTMOVE_POLYLINE_POINTS:
            sub_exterior = sub_poly.exterior
        else:
            sub_exterior, _ = find_min_simplify_tolerance(
                sub_poly.exterior, max_coords=MAX_RIGHTMOVE_POLYLINE_POINTS
            )
        # Check if simplified polygon is valid
        if Polygon(sub_exterior).area < 1e-9:
            continue

        results.append(sub_exterior)

    return results


# ============================================================================
# API Functions
# ============================================================================


async def fetch_journey_results(
    client: tfl.api.Tfl, lon: float, lat: float, query_lon: float, query_lat: float
) -> int | None:
    """Fetch the minimum TfL journey duration from a property to a destination.

    Args:
        client: An authenticated TfL API client.
        lon: Longitude of the origin (property location) in WGS84.
        lat: Latitude of the origin (property location) in WGS84.
        query_lon: Longitude of the destination in WGS84.
        query_lat: Latitude of the destination in WGS84.

    Returns:
        The minimum journey duration in minutes, or ``None`` if the journey
        could not be determined (disambiguation result or API error).
    """
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


async def get_property_ids_in_area(
    coords: list[LatLon],
    channel: Literal["RENT", "BUY"] = "RENT",
    depth: int = 0,
    *,
    semaphore: asyncio.Semaphore,
    min_price: int | None = None,
    max_price: int | None = None,
    seen_ids: frozenset[int] = frozenset(),
    predicate: Callable[[rightmove.models.MapProperty], bool] | None = None,
) -> list[rightmove.models.MapProperty]:
    """Fetch all Rightmove properties within a WGS84 polygon, subdividing as needed.

    Uses the listing search endpoint (sorted by most-recent) with incremental
    early-exit: pagination stops as soon as a full page consists entirely of
    property IDs already present in ``seen_ids``, minimising requests on
    repeat runs.

    If the coordinate count exceeds ``MAX_RIGHTMOVE_POLYLINE_POINTS``, or if
    the total result count exceeds :data:`rightmove.api.SEARCH_LIST_MAX_RESULTS`
    and no early exit occurred, the polygon is split into quadrants and the
    search is retried recursively.

    Args:
        coords: Exterior ring of the search area as ``LatLon`` values in WGS84.
        channel: Rightmove listing channel, either ``"RENT"`` or ``"BUY"``.
            Defaults to ``"RENT"``.
        depth: Current recursion depth (used for logging). Defaults to 0.
        min_price: Minimum price passed to the Rightmove API (monthly PCM for
            RENT, purchase price for BUY).  ``None`` means no lower bound.
        max_price: Maximum price passed to the Rightmove API.  ``None`` means
            no upper bound.
        seen_ids: Property IDs observed in previous pipeline runs.  Used to
            trigger early-exit when an all-seen page is encountered.
        predicate: Optional callable applied to each fetched property.  Only
            properties for which the predicate returns ``True`` are included
            in the returned list.

    Returns:
        A deduplicated list of properties within the search polygon that
        satisfy ``predicate`` (if provided).
    """
    rightmove_client = rightmove.api.Rightmove()
    # Ensure coords limit
    if len(coords) > MAX_RIGHTMOVE_POLYLINE_POINTS:
        exterior = LinearRing([(c.lon, c.lat) for c in coords])
        sub_exteriors = _subdivide_exterior(exterior)
        results = []
        for sub_exterior in sub_exteriors:
            sub_coords = [LatLon(lat=y, lon=x) for x, y in sub_exterior.coords]
            results.extend(
                property_location
                for property_location in await get_property_ids_in_area(
                    sub_coords,
                    channel=channel,
                    depth=depth + 1,
                    semaphore=semaphore,
                    min_price=min_price,
                    max_price=max_price,
                    seen_ids=seen_ids,
                    predicate=predicate,
                )
                if not any(result.id == property_location.id for result in results)
            )
        return results
    else:
        async with semaphore:
            (
                search_results,
                count,
                stopped_early,
            ) = await rightmove_client.search_incremental(
                rightmove.api.SearchQuery(
                    location_identifier=rightmove.api.polyline_identifier(
                        [(c.lat, c.lon) for c in coords]
                    ),
                    is_fetching=True,
                    channel=channel,
                    sort_type=rightmove.api.SortType.MOST_RECENT,
                    min_price=min_price or 0,
                    max_price=max_price,
                ),
                seen_ids=seen_ids,
            )
        if not stopped_early and count > rightmove.api.SEARCH_LIST_MAX_RESULTS:
            logger.info(
                "Count %d > %d, subdividing (depth %d).",
                count,
                rightmove.api.SEARCH_LIST_MAX_RESULTS,
                depth,
            )
            exterior = LinearRing([(c.lon, c.lat) for c in coords])
            sub_exteriors = _subdivide_exterior(exterior)
            results = []
            for sub_exterior in sub_exteriors:
                sub_coords = [LatLon(lat=y, lon=x) for x, y in sub_exterior.coords]
                results.extend(
                    property_location
                    for property_location in await get_property_ids_in_area(
                        sub_coords,
                        channel=channel,
                        depth=depth + 1,
                        semaphore=semaphore,
                        min_price=min_price,
                        max_price=max_price,
                        seen_ids=seen_ids,
                        predicate=predicate,
                    )
                    if not any(result.id == property_location.id for result in results)
                )
            return results
        else:
            if predicate is not None:
                return [p for p in search_results if predicate(p)]
            return search_results
