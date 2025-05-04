import argparse
import itertools
import json
import logging

import flathunt.io
import flathunt.property_viewer
import rightmove.models

_LOGGER = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--properties", type=str)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, encoding="utf-8")
    _LOGGER.setLevel(logging.INFO)
    _LOGGER.addHandler(logging.StreamHandler())

    properties = flathunt.io.load_json(list[rightmove.models.Property], args.properties)

    with open("locations.json", "r") as file:
        locations = {key: tuple(value) for key, value in json.load(file).items()}

    _LOGGER.info("Loaded %s properties", len(properties))
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
