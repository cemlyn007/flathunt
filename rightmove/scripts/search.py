import argparse
import json
import rightmove.app
import rightmove.property_cache


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", default=False)
    parser.add_argument("--search-locations", type=str, default="search_locations.json")
    args = parser.parse_args()

    commute_coordinates = {
        "Paddington Station": (51.5167, 0.1769),
        "Big Ben": (51.5007, 0.1246),
    }
    cache = rightmove.property_cache.PropertyCache("history.json", args.reset)
    app = rightmove.app.App(
        list(commute_coordinates.values()),
        cache,
    )
    # These location IDs can be found by inspecting the URL
    # of a search result on rightmove.
    with open(args.search_locations, "r") as file:
        search_locations = json.load(file)
    search_prices = {
        "Aldgate East Station": 2000,
        "Islington": 2500,
        "Barbican Station": 3000,
    }

    try:
        for location, location_id in search_locations.items():
            print(f"Searching for properties near {location}...", flush=True)
            app.search(location_id, search_prices.get(location, 2200), 0.5, 7)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
