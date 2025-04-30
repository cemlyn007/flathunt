import argparse
from collections.abc import Iterable, Iterator
import os
import rightmove.models
import json
import pathlib


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
        with open(filepath, "r") as file:
            content = json.load(file)
        search_results: list[rightmove.models.Property] = [
            rightmove.models.Property.model_validate(search_property)
            for search_property in content
        ]
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


def _save_search_results(
    filepath: str, properties: list[rightmove.models.Property]
) -> None:
    """Save search results to a file."""
    path = pathlib.Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([property.model_dump(mode="json") for property in properties])
    )


def _main(search_results_filepath: Iterable[str], output_filepath: str) -> None:
    _save_search_results(
        output_filepath,
        _merge_search_results(_load_search_results(search_results_filepath)),
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
