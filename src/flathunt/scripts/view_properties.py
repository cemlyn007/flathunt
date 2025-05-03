import argparse
import itertools
import json
import logging

import flathunt.property_viewer
import rightmove.models

_LOGGER = logging.getLogger(__name__)


def _load_properties(
    filepath: str,
) -> list[rightmove.models.Property]:
    """Load properties from a JSON file."""
    with open(filepath, "r") as file:
        properties: list[rightmove.models.Property] = [
            rightmove.models.Property.model_validate(search_property)
            for search_property in json.load(file)
        ]
    return properties


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--properties", type=str)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, encoding="utf-8")
    _LOGGER.setLevel(logging.INFO)
    _LOGGER.addHandler(logging.StreamHandler())

    properties = _load_properties(args.properties)

    with open("locations.json", "r") as file:
        locations = {key: tuple(value) for key, value in json.load(file).items()}

    viewer = flathunt.property_viewer.Viewer(
        commute_coordinates=list(locations.values())
    )
    try:
        for property_batch in itertools.batched(properties, 3):
            for property in property_batch:
                _LOGGER.info(
                    "Property %s (%s %s) at %s",
                    property.id,
                    property.price.amount if property.price else "N/A",
                    property.price.frequency if property.price else "N/A",
                    property.display_address,
                )
                viewer(property)
            input("Press enter to continue to the next batch of properties...")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    try:
        main()
    finally:
        logging.shutdown()
