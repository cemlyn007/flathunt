import argparse
import datetime
import itertools
import json
import operator
import os
import random
import time
from collections.abc import Collection, Iterable

import tenacity
import tqdm

import flathunt.io
import rightmove.api
import rightmove.models


def _map_search(
    api: rightmove.api.Rightmove,
    code_boundaries: Collection[tuple[str, list[tuple[float, float]]]],
    historical_properties: Iterable[rightmove.models.Property],
) -> list[rightmove.models.Property]:
    property_ids: set[int] = set()
    with tqdm.tqdm(
        total=len(code_boundaries), desc="Searching for IDs"
    ) as progress_bar:
        for code, polyline in sorted(code_boundaries):
            progress_bar.set_description(f'Searching for IDs in "{code}"')

            min_long = min(vertex[0] for vertex in polyline)
            min_lat = min(vertex[1] for vertex in polyline)
            max_long = max(vertex[0] for vertex in polyline)
            max_lat = max(vertex[1] for vertex in polyline)

            # Call our recursive search function with the initial bounding box
            more_property_locations = _search_area_recursive(
                api, ((min_lat, min_long), (max_lat, max_long))
            )
            property_ids.update(more_property_locations)
            progress_bar.update(1)

    for property in historical_properties:
        if (
            property.id in property_ids
            and property.lozenge_model
            and any(
                lozenge.type == "LET_AGREED"
                for lozenge in property.lozenge_model.matching_lozenges
            )
        ):
            property_ids.remove(property.id)

    property_ids_list = list(property_ids)
    property_ids_list.sort()

    properties = []
    with tqdm.tqdm(
        total=len(property_ids_list), desc="Downloading Results"
    ) as progress_bar:
        for batched_location_ids in itertools.batched(
            property_ids_list, rightmove.api.SEARCH_BY_IDS_MAX_RESULTS
        ):
            more_properties = api.search_by_ids(
                batched_location_ids,
                "RENT",
            )
            properties.extend(more_properties)
            progress_bar.update(len(more_properties))
            _fast_sleep()
    return properties


def _search_area_recursive(
    api: rightmove.api.Rightmove,
    bounding_box: tuple[tuple[float, float], tuple[float, float]],
) -> set[int]:
    min_point, max_point = bounding_box

    # Create polyline for this bounding box
    polyline = _create_bounding_box_polyline(min_point, max_point)
    location_identifier = rightmove.api.polyline_identifier(polyline)

    # Configure the search query
    query = rightmove.api.SearchQuery(
        location_identifier=location_identifier,
        is_fetching=True,
        include_let_agreed=True,
        view_type="MAP",  # Ensure we're using MAP view for accurate counting
    )

    # Check if we'd get too many results
    property_locations, result_count = api.map_search(query)
    _fast_sleep()
    if result_count > rightmove.api.SEARCH_MAP_MAX_RESULTS:
        # Subdivide this area into 4 quadrants
        min_x, min_y = min_point
        max_x, max_y = max_point
        quadrants = _subdivide_bounding_box(min_x, min_y, max_x, max_y)

        # Recursively search each quadrant
        results = set()
        for i, quadrant in enumerate(quadrants):
            quadrant_results = _search_area_recursive(
                api,
                quadrant,
            )
            results.update(quadrant_results)
            _fast_sleep()

        return results

    return set(map(operator.attrgetter("id"), property_locations))


def _subdivide_bounding_box(
    min_x: float, min_y: float, max_x: float, max_y: float
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    mid_x = (min_x + max_x) / 2
    mid_y = (min_y + max_y) / 2

    # Create 4 quadrants
    # Format: ((min_long, min_lat), (max_long, max_lat))
    return [
        # Southwest quadrant
        ((min_x, min_y), (mid_x, mid_y)),
        # Southeast quadrant
        ((mid_x, min_y), (max_x, mid_y)),
        # Northwest quadrant
        ((min_x, mid_y), (max_x, max_y)),
        # Northeast quadrant
        ((mid_x, mid_y), (max_x, max_y)),
    ]


def _create_bounding_box_polyline(
    min_point: tuple[float, float], max_point: tuple[float, float]
) -> list[tuple[float, float]]:
    """Create a polyline for a bounding box.

    Args:
        min_point: (min_long, min_lat)
        max_point: (max_long, max_lat)

    Returns:
        Polyline vertices as list of coordinate tuples
    """
    min_x, min_y = min_point
    max_x, max_y = max_point
    # Create closed polygon (5 points, with first point repeated at the end)
    return [
        (min_x, min_y),  # Southwest
        (max_x, min_y),  # Southeast
        (max_x, max_y),  # Northeast
        (min_x, max_y),  # Northwest
        (min_x, min_y),  # Close the loop
    ]


def _fast_sleep():
    """Random sleep to avoid hitting the API too fast."""
    if sleep := random.random():
        time.sleep(sleep)


if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser("Fetch Rightmove Properties")
    argument_parser.add_argument(
        "--boundaries", type=str, required=True, help="Boundaries JSON file"
    )
    argument_parser.add_argument(
        "--output", type=str, default="", help="Save JSON file location"
    )
    argument_parser.add_argument(
        "--properties", type=str, default="", help="Properties JSON file"
    )
    arguments = argument_parser.parse_args()
    filepath = arguments.boundaries
    output = arguments.output
    if (extension := os.path.splitext(output)[1]) != ".json":
        timestamp = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        output = os.path.join(output, f"{timestamp}.json")

    with open(filepath, "r") as file:
        post_code_boundaries: dict[str, list[tuple[float, float]]] = json.load(file)

    if arguments.properties:
        historical_properties = flathunt.io.load_json(
            list[rightmove.models.Property], arguments.properties
        )
    else:
        historical_properties = []

    api = rightmove.api.Rightmove(
        retrying=tenacity.Retrying(
            retry=tenacity.retry_if_exception_type(rightmove.api.HTTPError)
        )
    )
    properties = _map_search(
        api,
        list(post_code_boundaries.items()),
        historical_properties,
    )
    flathunt.io.save_json(list[rightmove.models.Property], properties, output)
