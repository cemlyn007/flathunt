from collections.abc import Sequence
import os
import matplotlib.cm
import json
import logging
import statistics
from matplotlib import pyplot as plt
from matplotlib.collections import PatchCollection
import argparse
import tqdm
import rightmove.models
import matplotlib.colors

import numpy as np
from matplotlib import patches, text
from matplotlib.path import Path
import concurrent.futures


def _create_artists(
    boundaries: dict[str, list[list[list[tuple[float, float]]]]],
) -> tuple[list[patches.PathPatch], list[text.Text]]:
    polygons = []
    texts = []
    for post_code_area, multi_coordinates in boundaries.items():
        vertices = []
        codes = []
        for multi_polylines in multi_coordinates:
            for polyline in multi_polylines:
                for vertex_index, vertex in enumerate(polyline):
                    vertices.append(vertex)
                    codes.append(Path.MOVETO if vertex_index == 0 else Path.LINETO)
        patch_patch = patches.PathPatch(
            Path(
                vertices,
                codes,
                closed=True,
                readonly=True,
            ),
            fill=False,
        )
        polygons.append(patch_patch)
        texts.append(
            text.Text(
                statistics.mean(point[0] for point in vertices),
                statistics.mean(point[1] for point in vertices),
                post_code_area,
                fontsize=4,
                ha="center",
                va="center",
                color=(0, 0, 0, 0.5),
                bbox=dict(
                    boxstyle="round,pad=0.3", edgecolor="black", facecolor="white"
                ),
            )
        )
        texts[-1].set_visible(False)
    return polygons, texts


def _assign_properties_to_region(
    properties: list[rightmove.models.Property],
    polygons,
    ordered_keys: Sequence[str],
) -> dict[str, list[rightmove.models.Property]]:
    grouped_search_results: dict[str, list[rightmove.models.Property]] = {}
    points = [
        (
            search_property.location.longitude,
            search_property.location.latitude,
        )
        for search_property in properties
    ]
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=(os.cpu_count() or 2) - 1
    ) as executor:
        futures = [
            executor.submit(
                lambda i: (
                    i,
                    np.argwhere(polygons[i].get_path().contains_points(points)).ravel(),
                ),
                index,
            )
            for index in range(len(polygons))
        ]
        for future in tqdm.tqdm(
            concurrent.futures.as_completed(futures),
            total=len(futures),
            desc="Mapping properties to regions",
        ):
            result = future.result()
            result: tuple[int, np.ndarray]
            index, point_indices = result
            for point_index in point_indices:
                boundary_name = ordered_keys[index]
                grouped_search_results.setdefault(boundary_name, []).append(
                    properties[point_index]
                )
    return grouped_search_results


def _group_monthly_rent(
    grouped_search_results: dict[str, list[rightmove.models.Property]],
) -> dict[str, list[float]]:
    region_monthly_prices = {}
    for key, search_results in grouped_search_results.items():
        # Note: Ads have already been filtered out.
        prices = []
        for search_property in search_results:
            if search_property.price is None:
                logging.warning("Property %s has no price", search_property.id)
                continue
            # else...
            match search_property.price.frequency:
                case "monthly":
                    amount = search_property.price.amount
                case "weekly":
                    amount = search_property.price.amount * 52 / 12
                case "daily":
                    amount = search_property.price.amount * 365 / 12
                case "yearly":
                    amount = search_property.price.amount / 12
                case _:
                    raise ValueError(
                        f"Unknown frequency {search_property.price.frequency}"
                    )

            prices.append(amount)
        if prices:
            region_monthly_prices[key] = prices
    return region_monthly_prices


def _update_artists(
    polygons: list[patches.PathPatch],
    texts: list[text.Text],
    boundaries: list[str],
    key_monthly_prices: dict[str, list[float]],
    max_price: float,
    show_text: bool,
) -> None:
    for index, code in enumerate(boundaries):
        sum_price = 0
        count = 0
        if code in key_monthly_prices:
            sum_price += statistics.mean(key_monthly_prices[code])
            count += 1
        if count > 0:
            mean_price = sum_price / count
            face_color = (
                matplotlib.colormaps["inferno"](mean_price / max_price)
                if count
                else None
            )
            polygons[index].set_facecolor(face_color)
            polygons[index].set_fill(True)
            texts[index].set_visible(show_text)
        else:
            polygons[index].set_facecolor((0, 0, 0, 0))
            polygons[index].set_fill(False)
            texts[index].set_visible(False)


def _plot(
    polygons: list[patches.PathPatch],
    texts: list[text.Text],
    min_price: float,
    max_price: float,
    show_open_door_logistics: bool,
) -> None:
    figure, axis = plt.subplots(figsize=(10, 10))
    axis.add_collection(PatchCollection(polygons, match_original=True))
    for t in texts:
        axis.add_artist(t)
    axis.set_aspect("equal", adjustable="box")
    axis.autoscale_view()
    figure.colorbar(
        matplotlib.cm.ScalarMappable(
            norm=matplotlib.colors.Normalize(vmin=min_price, vmax=max_price),
            cmap=matplotlib.colormaps["inferno"],
        ),
        ax=axis,
        label="Average monthly rent",
    )
    if show_open_door_logistics:
        figure.text(
            0.5,
            0.05,
            "Postcode sector boundaries from www.opendoorlogistics.com",
            ha="center",
        )
    plt.show(block=True)


def _main(
    boundaries_file_path: str,
    properties_file_path: str,
    max_price: float,
    show_text: bool,
    show_open_door_logistics: bool,
) -> None:
    with open(boundaries_file_path, "r") as file:
        boundaries: dict[str, list[list[list[tuple[float, float]]]]] = json.load(file)
    with open(properties_file_path, "r") as file:
        properties: list[rightmove.models.Property] = [
            rightmove.models.Property.model_validate(search_property)
            for search_property in json.load(file)
        ]
    ordered_keys = list(boundaries)
    polygons, texts = _create_artists(boundaries=boundaries)
    grouped_search_results: dict[str, list[rightmove.models.Property]] = (
        _assign_properties_to_region(
            properties=properties,
            polygons=polygons,
            ordered_keys=ordered_keys,
        )
    )
    key_monthly_prices = _group_monthly_rent(
        grouped_search_results=grouped_search_results,
    )
    min_price = min(statistics.mean(prices) for prices in key_monthly_prices.values())
    max_price = min(
        max(statistics.mean(prices) for prices in key_monthly_prices.values()),
        max_price,
    )
    _update_artists(
        polygons=polygons,
        texts=texts,
        boundaries=ordered_keys,
        key_monthly_prices=key_monthly_prices,
        max_price=max_price,
        show_text=show_text,
    )
    _plot(
        polygons=polygons,
        texts=texts,
        min_price=min_price,
        max_price=max_price,
        show_open_door_logistics=show_open_door_logistics,
    )


if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser("Fetch Rightmove Properties")
    argument_parser.add_argument(
        "--boundaries", type=str, required=True, help="Boundaries JSON file"
    )
    argument_parser.add_argument(
        "--properties", type=str, required=True, help="Properties JSON file"
    )
    argument_parser.add_argument(
        "--max-price", type=str, required=True, help="Properties JSON file"
    )
    argument_parser.add_argument(
        "--show-text",
        action="store_true",
        help="Show text labels on polygons",
        default=False,
    )
    argument_parser.add_argument(
        "--open-door-logistics",
        action="store_true",
        help="Add Open Door Logistics reference to the plot",
        default=False,
    )
    arguments = argument_parser.parse_args()
    _main(
        boundaries_file_path=arguments.boundaries,
        properties_file_path=arguments.properties,
        max_price=float(arguments.max_price),
        show_text=arguments.show_text,
        show_open_door_logistics=arguments.open_door_logistics,
    )
