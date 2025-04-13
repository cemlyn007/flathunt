from pathlib import Path
from collections.abc import Collection, Iterable
import json
import pathlib
from typing import Literal
import tqdm
import ons.pd
import argparse
import operator
import random
import time


import rightmove.api
import rightmove.models
import logging

CACHE_DIRECTORY = pathlib.Path("cache")


def _fast_sleep():
    """Random sleep to avoid hitting the API too fast."""
    if sleep := random.random():
        time.sleep(sleep)


def _slow_sleep():
    """Random sleep to avoid hitting the API too fast."""
    if (sleep := random.gauss(10.0, 5.0)) > 0:
        time.sleep(sleep)


def get_identifiers(codes: Collection[str]) -> dict[str, str]:
    """Get district identifiers from codes."""
    path = CACHE_DIRECTORY / "lookups.json"
    if path.exists():
        logging.info("Using cached lookups")
        lookups = get_cached_lookups(path)
    else:
        lookups = {}
    selected_lookups = {
        district_code: lookup_match
        for district_code, lookup_match in lookups.items()
        if district_code in codes
    }
    missing_codes = set(codes) - set(selected_lookups.keys())
    if missing_codes:
        more_lookups = lookup(missing_codes)
        lookups.update(more_lookups)
        _save_lookups(path, lookups)
        selected_lookups.update(more_lookups)
    return {
        district_code: lookup_match.location_identifier
        for district_code, lookup_match in selected_lookups.items()
    }


def _save_lookups(
    path: Path,
    district_code_lookups: dict[str, rightmove.models.LookupMatch],
):
    """Save district code lookups to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                district_code: lookup_match.model_dump(mode="json")
                for district_code, lookup_match in district_code_lookups.items()
            }
        )
    )


def lookup(district_codes: Iterable[str]):
    """Get district identifiers from district codes."""
    district_code_lookups: dict[str, rightmove.models.LookupMatch] = {}
    for district_code in tqdm.tqdm(district_codes):
        (lookup_match,) = api.lookup(district_code, limit=1).matches
        if not (
            lookup_match.display_name == district_code
            or lookup_match.display_name.startswith(f"{district_code},")
        ):
            logging.warning(
                f"Skipping district code {district_code} because it does not match lookup {lookup_match.display_name}"
            )
            continue
        district_code_lookups[district_code] = lookup_match
        _fast_sleep()
    return district_code_lookups


def get_cached_lookups(
    path: Path,
) -> dict[str, rightmove.models.LookupMatch]:
    return {
        district_code: rightmove.models.LookupMatch.model_validate(lookup_match)
        for district_code, lookup_match in json.loads(path.read_text()).items()
    }


def search(
    post_codes: Collection[str],
    resolution: Literal["district", "sub_district", "sector", "post_code"] = "district",
):
    if resolution == "district":
        codes = {ons.pd.district_code(post_code) for post_code in post_codes}
        next_resolution = "sub_district"
    elif resolution == "sub_district":
        codes = {ons.pd.sub_district_code(post_code) for post_code in post_codes}
        next_resolution = "sector"
    elif resolution == "sector":
        codes = {ons.pd.sector_code(post_code) for post_code in post_codes}
        next_resolution = "post_code"
    elif resolution == "post_code":
        codes = post_codes
        next_resolution = None
    else:
        raise ValueError(f"Invalid resolution: {resolution}")
    identifiers = get_identifiers(codes)
    codes_with_missing_results = [code for code in codes if code not in identifiers]
    search_results = _search(list(identifiers.values()))
    codes_with_missing_results.extend(
        (
            next(
                code
                for code, other_identifier in identifiers.items()
                if other_identifier == identifier
            )
            for identifier, properties in search_results.items()
            if len(properties) >= rightmove.api.SEARCH_MAX_RESULTS
        )
    )
    if codes_with_missing_results:
        if next_resolution is None:
            logging.warning(
                f"Post codes with missing results: {sorted(codes_with_missing_results)}"
            )
            return search_results
        missing_post_codes = [
            post_code
            for post_code in post_codes
            if {
                "district": ons.pd.district_code,
                "sub_district": ons.pd.sub_district_code,
                "sector": ons.pd.sector_code,
            }[resolution](post_code)
            in codes_with_missing_results
        ]
        more_search_results = search(missing_post_codes, next_resolution)
        search_results.update(more_search_results)
    return search_results


def _search(
    location_identifiers: Iterable[str],
):
    search_results: dict[str, list[rightmove.models.Property]] = {}
    for location_identifier in tqdm.tqdm(location_identifiers, desc="Searching"):
        query = rightmove.api.SearchQuery(
            location_identifier=location_identifier,
            is_fetching=True,
            include_let_agreed=True,
        )
        search_results[location_identifier] = api.search(query)
        _slow_sleep()
    return search_results


def _save_search_results(
    identifier_properties: dict[str, list[rightmove.models.Property]],
) -> None:
    """Save search results to a file."""
    path = CACHE_DIRECTORY / "search_results.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                location_identifier: [
                    property.model_dump(mode="json") for property in properties
                ]
                for location_identifier, properties in identifier_properties.items()
            }
        )
    )


if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser("Fetch London Rightmove Properties")
    argument_parser.add_argument(
        "--onspds", type=str, required=True, help="ONSPD file path"
    )
    arguments = argument_parser.parse_args()

    file_path = arguments.onspds

    post_codes = list(
        map(
            operator.itemgetter(0),
            ons.pd.read_london_active_post_code_centroids(file_path),
        )
    )
    for post_code in post_codes:
        ons.pd.assert_valid_postcode(post_code)

    # Slim for debugging
    # post_codes = [post_code for post_code in post_codes if post_code.startswith("WD2")]

    api = rightmove.api.Rightmove()

    search_results = search(post_codes)
    _save_search_results(search_results)
