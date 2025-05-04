import argparse
import ast
import datetime
import json
import logging
import os
from typing import cast

import tenacity

import flathunt.cached_app
import flathunt.io
import flathunt.rate_limiter
import rightmove.models
import rightmove.property_cache
import tfl.api

_LOGGER = logging.getLogger(__name__)


def rate_limit_wait(retry_state: tenacity.RetryCallState) -> int:
    outcome = retry_state.outcome
    if not outcome:
        raise ValueError("RetryCallState has no outcome")
    exception = outcome.exception()
    if not isinstance(exception, tfl.api.RateLimitError):
        raise ValueError(
            "RetryCallState exception is not RateLimitError"
        ) from exception
    return exception.wait


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", default=False)
    parser.add_argument("--properties", type=str)
    parser.add_argument("--default-max-price", type=int, default=2200)
    parser.add_argument("--max-journey-minutes", type=int, default=45)
    parser.add_argument("--max-days-since-added", type=int, default=7)
    parser.add_argument("--min-square-meters", type=int, default=0)
    parser.add_argument("--sort-center", type=str, default=None)
    parser.add_argument("--output", type=str, default="properties.json")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, encoding="utf-8")
    for logger in (_LOGGER, flathunt.cached_app.logger):
        logger.setLevel(logging.INFO)
        logger.addHandler(logging.StreamHandler())

    properties = flathunt.io.load_json(list[rightmove.models.Property], args.properties)

    with open("locations.json", "r") as file:
        locations = {key: tuple(value) for key, value in json.load(file).items()}

    property_cache = rightmove.property_cache.PropertyCache("history.json", args.reset)
    rate_limiter = flathunt.rate_limiter.RateLimiter(max_calls=500, interval=60)

    http_error_retry = tenacity.Retrying(
        wait=tenacity.wait_exponential_jitter(max=90),
        stop=tenacity.stop_after_attempt(3),
        retry=tenacity.retry_if_exception_type(
            (
                tfl.api.NotFoundError,
                tfl.api.InternalServerError,
                tfl.api.BadGatewayError,
            )
        ),
        before_sleep=tenacity.before_sleep_log(_LOGGER, logging.ERROR),
    )
    rate_limit_retry = tenacity.Retrying(
        wait=rate_limit_wait,
        stop=tenacity.stop_after_attempt(3),
        retry=tenacity.retry_if_exception_type(tfl.api.RateLimitError),
        before_sleep=tenacity.before_sleep_log(_LOGGER, logging.INFO),
    )
    tfl_api = cast(
        tfl.api.Tfl,
        http_error_retry.wraps(
            rate_limit_retry.wraps(
                rate_limiter(tfl.api.Tfl(app_key=os.environ["FLATHUNT__TFL_API_KEY"]))
            )
        ),
    )
    app = flathunt.cached_app.App(
        list(locations.values()),
        property_cache,
        journey_cache=None,
        tfl_api=tfl_api,
        progress_bar=True,
    )
    if args.sort_center:
        sort_center = ast.literal_eval(args.sort_center)
        if not isinstance(sort_center, tuple) or len(sort_center) != 2:
            raise ValueError("sort_center must be a tuple of (longitude, latitude)")
    else:
        sort_center = None
    properties.sort(
        key=lambda property: (
            (
                (
                    (
                        (property.location.latitude - sort_center[0]) ** 2
                        + (property.location.longitude - sort_center[1]) ** 2
                    )
                    ** 0.5
                )
                if sort_center
                else 0
            ),
            (
                -property.first_visible_date.timestamp()
                if property.first_visible_date
                else 0
            ),
        ),
    )
    appropiate_properties = []
    try:
        for property in app.search(
            properties,
            args.default_max_price,
            args.max_days_since_added,
            journey_coordinates=locations,
            max_journey_timedelta=datetime.timedelta(minutes=args.max_journey_minutes),
            min_square_meters=args.min_square_meters,
        ):
            appropiate_properties.append(property)
    except KeyboardInterrupt:
        pass
    finally:
        if appropiate_properties:
            flathunt.io.save_json(
                list[rightmove.models.Property], appropiate_properties, args.output
            )


if __name__ == "__main__":
    try:
        main()
    finally:
        logging.shutdown()
