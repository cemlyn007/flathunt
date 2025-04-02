import argparse
import datetime
import json
import os
import rightmove.property_cache
import flathunt.app
import logging


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", default=False)
    parser.add_argument("--search-locations", type=str, default="search_locations.json")
    parser.add_argument("--default-max-price", type=int, default=2200)
    parser.add_argument("--max-journey-minutes", type=int, default=45)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, encoding="utf-8")
    flathunt.app.logger.setLevel(logging.INFO)
    flathunt.app.logger.addHandler(logging.StreamHandler())

    with open("locations.json", "r") as file:
        locations = json.load(file)

    with open("search_location_prices.json", "r") as file:
        search_location_prices = json.load(file)

    cache = rightmove.property_cache.PropertyCache("history.json", args.reset)
    rightmove_app = flathunt.app.App(
        list(locations.values()), cache, tfl_app_key=os.environ["FLATHUNT__TFL_API_KEY"]
    )
    # These location IDs can be found by inspecting the URL
    # of a search result on rightmove.
    with open(args.search_locations, "r") as file:
        search_locations = json.load(file)

    try:
        for location, location_id in search_locations.items():
            print(f"Searching for properties near {location}...", flush=True)
            rightmove_app.search(
                location,
                location_id,
                search_location_prices.get(location, args.default_max_price),
                0.5,
                7,
                journey_coordinates=locations,
                max_journey_timedelta=datetime.timedelta(
                    minutes=args.max_journey_minutes
                ),
            )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    try:
        main()
    finally:
        logging.shutdown()
