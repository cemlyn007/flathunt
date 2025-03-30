import argparse
import rightmove.app
import rightmove.property_cache


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", default=False)
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
    search_locations = {
        "Aldgate East Station": "STATION^143",
        "Tower Hill Station": "STATION^9290",
        "Barbican Station": "STATION^569",
        "Angel Station": "STATION^245",
        "Victoria Station": "STATION^9491",
        "Pimlico Station": "STATION^7232",
        "Liverpool Street Station": "STATION^5615",
        "Regent's Park": "REGION^96921",
        "Paddington Station": "STATION^6965",
        "Royal Oak Station": "STATION^7832",
        "Farringdon Station": "STATION^3431",
        "Kilburn Station": "STATION^5120",
        "Holborn Station": "STATION^4655",
        "London Bridge Station": "STATION^5792",
        "Green Park Station": "STATION^3971",
        "Lancaster Gate Station": "STATION^5354",
        "Baker Street Station": "STATION^488",
        "Vauxhall Station": "STATION^9485",
        "Canning Town Station": "STATION^1733",
        "Islington": "REGION^93965",
        "Maida Value Station": "STATION^5945",
        "Hampstead Station": "STATION^4190",
        "Notting Hill Gate Station": "STATION^6818",
        "Caledonian Road Station": "STATION^1679",
        "Holloway Road Station": "STATION^4670",
    }
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
