import json
import os
import rightmove.api
import argparse
import logging

DEFAULT_FILE_PATH = "search_locations.json"

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--file", default=DEFAULT_FILE_PATH, help="Path to the search locations file."
    )
    parser.add_argument("--locations", nargs="+", default=[])
    arguments = parser.parse_args()
    file_path = arguments.file
    locations = arguments.locations
    if not locations:
        print("No locations provided.")
        return

    api = rightmove.api.Rightmove()
    entries = {}
    for location in locations:
        logger.info(f"Searching for '{location}'...")
        result = api.lookup(location)
        logger.info(f"Result: {result}")
        matches = result["matches"]

        locations = {
            location_metadata["displayName"]: location_metadata["type"]
            + "^"
            + location_metadata["id"]
            for location_metadata in matches
        }

        if len(locations) != len(matches):
            raise RuntimeError("Display names are not unique.")
        elif len(locations) == 0:
            logger.warning(f"No locations found for '{location}'.")
        elif len(locations) > 1:
            logger.warning("Multiple locations found:")
            locations_list = list(locations.items())
            for index, (display_name, location_id) in enumerate(locations_list):
                logger.warning(f"[{index}]  {display_name}: {location_id}")
            logger.warning("Please select one of the above locations.")
            selected_index = int(input("Enter the index of the selected location: "))
            if selected_index < 0 or selected_index >= len(locations_list):
                raise RuntimeError("Invalid index.")
            selected_location = locations_list[selected_index]
            location_id = selected_location[1]
            location_name = selected_location[0]
            locations = {location_name: location_id}
            logger.info(f"Selected location: {location_name}: {location_id}")
            continue

        entries.update(locations)

    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            existing_entries = json.load(file)
            entries.update(existing_entries)
    with open(file_path, "w") as file:
        json.dump(entries, file, indent=4)


if __name__ == "__main__":
    main()
