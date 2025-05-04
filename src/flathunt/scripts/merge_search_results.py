import argparse
import os
from collections.abc import Iterable, Iterator

import flathunt.io
import rightmove.models


def _load_search_results(
    filepaths: Iterable[str],
) -> Iterator[tuple[int, list[rightmove.models.Property]]]:
    """Load search results from multiple files."""
    for filepath in filepaths:
        file_name, _ = os.path.splitext(os.path.basename(filepath))
        if all(c.isdigit() for c in file_name):
            timestamp = int(file_name)
        else:
            raise ValueError(f"Invalid file name '{file_name}'. Expected a timestamp.")
        search_results = flathunt.io.load_json(
            list[rightmove.models.Property], filepath
        )
        yield timestamp, search_results


def _merge_search_results(
    search_results_iter: Iterator[tuple[int, list[rightmove.models.Property]]],
) -> list[rightmove.models.Property]:
    """Merge search results from multiple files."""
    property_id_timestamp = {}
    property_id_property = {}
    for timestamp, search_results in search_results_iter:
        for search_property in search_results:
            property_id = search_property.id
            current_timestamp = property_id_timestamp.get(property_id, float("-inf"))
            if current_timestamp < timestamp:
                property_id_timestamp[property_id] = timestamp
                property_id_property[property_id] = search_property
    return list(property_id_property.values())


def _main(search_results_filepath: Iterable[str], output_filepath: str) -> None:
    flathunt.io.save_json(
        list[rightmove.models.Property],
        _merge_search_results(_load_search_results(search_results_filepath)),
        output_filepath,
    )


if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser("Merge Search Results")
    argument_parser.add_argument(
        "--search-results",
        nargs="+",
        required=True,
        help="Search results JSON files of format <UTC timestamp>.json",
    )
    argument_parser.add_argument(
        "--output", type=str, required=True, help="Output file path"
    )
    arguments = argument_parser.parse_args()
    if (
        len(arguments.search_results) == 1
        and os.path.splitext(arguments.search_results[0])[1] != ".json"
    ):
        (directory,) = arguments.search_results
        directory: str
        search_results = [
            os.path.join(
                directory,
                file_name,
            )
            for file_name in os.listdir(directory)
        ]
    else:
        search_results: list[str] = arguments.search_results
    _main(
        search_results,
        arguments.output,
    )
