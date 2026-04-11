import asyncio
import logging
import os
from pathlib import Path

import dagster as dg
from pydantic import Field

import rightmove.models
from flathunt.coords import CommuteDest
from flathunt.defs.config import CommuteDestConfig
from flathunt.cache import ModelCache
from flathunt.filters import filter_by_commute
from flathunt.models import MatchedProperty
from flathunt.property_search import get_commute_durations

logger = logging.getLogger(__name__)

_JOURNEY_CACHE_TTL = 100 * 24 * 3600  # 100 days, matching the Streamlit app


class Config(dg.Config):
    queries: list[CommuteDestConfig]
    tfl_api_key: str = Field(
        default_factory=lambda: os.environ["FLATHUNT__TFL_API_KEY"]
    )
    cache_data_dir: str = "cache"


@dg.asset
def matched_property_ids(
    config: Config,
    candidate_properties: list[rightmove.models.MapProperty],
) -> list[MatchedProperty]:
    """Filter candidate properties by real TfL commute times and return matching IDs with durations.

    Journey durations from each property to every configured destination are
    fetched via the TfL Journey Planner API (cached in SQLite for 100 days).
    Only properties where *every* commute is within the corresponding
    ``max_duration`` are included in the output.

    Args:
        config: Asset configuration: commute destinations with time limits,
            TfL API key, and cache directory path.
        candidate_properties: Properties pre-filtered by area and basic
            constraints, as produced by the ``candidate_properties`` asset.

    Returns:
        A list of :class:`MatchedProperty` values pairing each passing property
        ID with its per-destination commute durations in minutes.
    """
    if not candidate_properties:
        logger.info("No candidate properties to evaluate.")
        return []

    queries = [
        CommuteDest(lon=q.lon, lat=q.lat, max_duration=q.max_duration)
        for q in config.queries
    ]

    cache_path = Path(config.cache_data_dir) / "journey_cache.db"
    logger.info("Opening journey cache at %s.", cache_path)
    journey_cache: ModelCache[int | None] = ModelCache(
        int | None, cache_path, ttl=_JOURNEY_CACHE_TTL
    )

    logger.info(
        "Fetching TfL commute durations for %d propert(ies) × %d destination(s).",
        len(candidate_properties),
        len(queries),
    )
    durations = asyncio.run(
        get_commute_durations(
            candidate_properties,
            queries,
            journey_cache,
            config.tfl_api_key,
        )
    )

    matched = filter_by_commute(candidate_properties, durations, queries)
    result = [
        MatchedProperty(property_id=prop.id, commute_durations=list(durs))
        for prop, durs in matched
    ]
    logger.info(
        "%d / %d propert(ies) matched all commute constraints.",
        len(result),
        len(candidate_properties),
    )
    return result
