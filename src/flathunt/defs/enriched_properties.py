import asyncio
import logging
import os
from pathlib import Path

import dagster as dg
import httpx
from pydantic import Field
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

import rightmove.api
import rightmove.models
from flathunt.cache import ModelCache
from flathunt.models import FinalProperty, MatchedProperty
from rightmove.description_extractor import (
    ExtractedPropertyInfo,
    PropertyDescriptionExtractor,
)
from rightmove.floor_plan import FloorPlanSizeExtractor

logger = logging.getLogger(__name__)

_FLOOR_PLAN_CACHE_TTL = 30 * 24 * 3600  # 30 days
_LEASEHOLD_CACHE_TTL = 30 * 24 * 3600  # 30 days
_PROPERTY_DETAILS_CACHE_TTL = 7 * 24 * 3600  # 7 days
_LLM_CONCURRENCY = 1
_LLM_CALL_INTERVAL = 15.0  # seconds between LLM calls
_DETAILS_CONCURRENCY = 3


def _is_rate_limit_error(exc: BaseException) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429


def _parse_display_size(display_size: str | None) -> float | None:
    """Return the floor area in square metres, or None if not present or not parseable."""
    if not display_size:
        return None
    if display_size.endswith(" sq. ft."):
        sq_ft = int(display_size.removesuffix(" sq. ft.").replace(",", ""))
        return sq_ft * 0.092903
    if display_size.endswith(" sqm"):
        return float(display_size.removesuffix(" sqm").replace(",", ""))
    return None


async def _get_floor_plan_sqm(
    prop_id: int,
    details: rightmove.models.PropertyDetails | None,
    cache: ModelCache[float | None],
    extractor: FloorPlanSizeExtractor,
    llm_semaphore: asyncio.Semaphore,
) -> float | None:
    """Return the floor area in sqm, using cache or LLM extraction.

    Only writes to the cache on a successful extraction attempt so that
    transient failures (network errors, rate limits) are retried on the
    next run rather than being permanently recorded as missing.
    """
    cache_key = str(prop_id)
    try:
        return cache.get(cache_key)
    except KeyError:
        pass

    @retry(
        retry=retry_if_exception(_is_rate_limit_error),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        stop=stop_after_attempt(6),
        reraise=True,
    )
    async def _extract_with_retry(image_data: bytes) -> float | None:
        async with llm_semaphore:
            size = await extractor.extract(image_data)
            await asyncio.sleep(_LLM_CALL_INTERVAL)
        return size.to_sqm() if size is not None else None

    sqm: float | None = None
    try:
        if details is None or not details.floorplans:
            logger.warning("Property %d has no floor plan URLs in page model.", prop_id)
        else:
            # TODO: attempt extraction on all floor plan images, not just the first
            floor_plan_url = details.floorplans[0].url
            async with httpx.AsyncClient() as client:
                response = await client.get(floor_plan_url, timeout=30.0)
                response.raise_for_status()
            sqm = await _extract_with_retry(response.content)
            if sqm is not None:
                logger.info("Extracted %.1f sqm for property %d.", sqm, prop_id)
            else:
                logger.info(
                    "No size annotation found in floor plan for property %d.", prop_id
                )
        cache.update([(cache_key, sqm)])
    except Exception:
        logger.exception(
            "Failed to extract floor plan size for property %d — keeping property.",
            prop_id,
        )

    return sqm


async def _get_description_info(
    prop_id: int,
    details: rightmove.models.PropertyDetails | None,
    cache: ModelCache[ExtractedPropertyInfo],
    extractor: PropertyDescriptionExtractor,
    llm_semaphore: asyncio.Semaphore,
) -> ExtractedPropertyInfo:
    """Return extracted property info, using cache or LLM extraction.

    Only writes to the cache on a successful extraction attempt so that
    transient failures (network errors, rate limits) are retried on the
    next run rather than being permanently recorded as missing.
    """
    cache_key = str(prop_id)
    try:
        return cache.get(cache_key)
    except KeyError:
        pass

    @retry(
        retry=retry_if_exception(_is_rate_limit_error),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        stop=stop_after_attempt(6),
        reraise=True,
    )
    async def _extract_with_retry(description: str) -> ExtractedPropertyInfo:
        async with llm_semaphore:
            info = await extractor.extract(description)
            await asyncio.sleep(_LLM_CALL_INTERVAL)
        return info

    info = ExtractedPropertyInfo()
    try:
        description = details.description if details else None
        if not description:
            logger.warning(
                "Property %d has no description for info extraction.", prop_id
            )
        else:
            info = await _extract_with_retry(description)
            logger.info(
                "Extracted description info for property %d: %s",
                prop_id,
                info.model_dump(exclude_none=True),
            )
        cache.update([(cache_key, info)])
    except Exception:
        logger.exception(
            "Failed to extract description info for property %d — keeping property.",
            prop_id,
        )

    return info


async def _process_property(
    prop: rightmove.models.MapProperty,
    matched: MatchedProperty,
    needs_extraction: bool,
    floor_plan_cache: ModelCache[float | None],
    description_info_cache: ModelCache[ExtractedPropertyInfo],
    details_cache: ModelCache[rightmove.models.PropertyDetails],
    extractor: FloorPlanSizeExtractor,
    description_extractor: PropertyDescriptionExtractor,
    rightmove_client: rightmove.api.Rightmove,
    details_semaphore: asyncio.Semaphore,
    llm_semaphore: asyncio.Semaphore,
) -> FinalProperty:
    """Fetch property details and optionally extract floor plan size, then build a FinalProperty."""
    details = None
    cache_key = str(prop.id)
    try:
        details = details_cache.get(cache_key)
        logger.debug("Property details cache hit for property %d.", prop.id)
    except KeyError:
        try:
            async with details_semaphore:
                details = await rightmove_client.get_property_details(prop.property_url)
            details_cache.update([(cache_key, details)])
        except Exception:
            logger.exception(
                "Failed to fetch property details for property %d.", prop.id
            )

    extracted_sqm: float | None = None
    if needs_extraction:
        extracted_sqm = await _get_floor_plan_sqm(
            prop.id, details, floor_plan_cache, extractor, llm_semaphore
        )
        await asyncio.sleep(_LLM_CALL_INTERVAL)

    api_years = details.years_remaining_on_lease if details else None
    desc_info = await _get_description_info(
        prop.id, details, description_info_cache, description_extractor, llm_semaphore
    )

    lc = details.living_costs if details else None
    return FinalProperty(
        id=prop.id,
        display_address=prop.display_address,
        price=prop.price,
        bedrooms=prop.bedrooms,
        bathrooms=prop.bathrooms,
        display_size=prop.display_size,
        extracted_sqm=extracted_sqm,
        property_url=prop.property_url,
        commute_durations=matched.commute_durations,
        council_tax_band=lc.council_tax_band if lc else None,
        annual_ground_rent=lc.annual_ground_rent if lc else None,
        ground_rent_review_period_in_years=(
            lc.ground_rent_review_period_in_years if lc else None
        ),
        ground_rent_percentage_increase=(
            lc.ground_rent_percentage_increase if lc else None
        ),
        annual_service_charge=lc.annual_service_charge if lc else None,
        tenure_type=details.tenure_type if details else None,
        years_remaining_on_lease=api_years,
        extracted_years_remaining_on_lease=desc_info.years_remaining_on_lease,
        extracted_tenure_type=desc_info.tenure_type,
        extracted_annual_service_charge=desc_info.annual_service_charge,
        extracted_annual_ground_rent=desc_info.annual_ground_rent,
        extracted_council_tax_band=desc_info.council_tax_band,
    )


class Config(dg.Config):
    min_square_meters: float = 0.0
    github_token: str = Field(default_factory=lambda: os.environ["GITHUB_TOKEN"])
    cache_data_dir: str = "cache"


@dg.asset
def enriched_properties(
    context: dg.AssetExecutionContext,
    config: Config,
    matched_property_ids: list[MatchedProperty],
    candidate_properties: list[rightmove.models.MapProperty],
) -> list[FinalProperty]:
    """Enrich matched properties with living costs and filter by floor area.

    Fetches the Rightmove property details page for every matched property to
    obtain living costs (council tax band, ground rent, service charge, tenure).
    For properties whose ``display_size`` is absent and that have exactly one
    floor plan image, the floor plan is passed to :class:`FloorPlanSizeExtractor`
    to read the size annotation.  LLM calls are serialised (one at a time) with a
    5-second gap between them.

    Properties where the floor area cannot be determined are kept.

    Args:
        config: Size threshold, GitHub token for the LLM, and cache directory.
        matched_property_ids: Properties that passed the commute filter, with
            per-destination durations, as produced by ``matched_property_ids``.
        candidate_properties: Full property objects from ``candidate_properties``.

    Returns:
        A list of :class:`FinalProperty` values containing all enriched data for
        properties whose floor area meets ``min_square_meters``.
    """
    if not matched_property_ids:
        return []

    matched_set = {m.property_id for m in matched_property_ids}
    props_by_id = {p.id: p for p in candidate_properties if p.id in matched_set}

    floor_plan_cache_path = Path(config.cache_data_dir) / "floor_plan_size_cache.db"
    floor_plan_cache: ModelCache[float | None] = ModelCache(
        float | None, floor_plan_cache_path, ttl=_FLOOR_PLAN_CACHE_TTL
    )

    details_cache_path = Path(config.cache_data_dir) / "property_details_cache.db"
    details_cache: ModelCache[rightmove.models.PropertyDetails] = ModelCache(
        rightmove.models.PropertyDetails,
        details_cache_path,
        ttl=_PROPERTY_DETAILS_CACHE_TTL,
    )

    description_info_cache_path = (
        Path(config.cache_data_dir) / "description_info_cache.db"
    )
    description_info_cache: ModelCache[ExtractedPropertyInfo] = ModelCache(
        ExtractedPropertyInfo,
        description_info_cache_path,
        ttl=_LEASEHOLD_CACHE_TTL,
    )

    extractor = FloorPlanSizeExtractor(token=config.github_token)
    description_extractor = PropertyDescriptionExtractor(token=config.github_token)
    rightmove_client = rightmove.api.Rightmove()

    async def _run_all() -> list[FinalProperty]:
        details_semaphore = asyncio.Semaphore(_DETAILS_CONCURRENCY)
        llm_semaphore = asyncio.Semaphore(_LLM_CONCURRENCY)
        tasks = []
        for matched in matched_property_ids:
            prop = props_by_id.get(matched.property_id)
            if prop is None:
                continue
            metadata_sqm = _parse_display_size(prop.display_size)
            needs_extraction = metadata_sqm is None and prop.number_of_floorplans == 1
            tasks.append(
                _process_property(
                    prop,
                    matched,
                    needs_extraction,
                    floor_plan_cache,
                    description_info_cache,
                    details_cache,
                    extractor,
                    description_extractor,
                    rightmove_client,
                    details_semaphore,
                    llm_semaphore,
                )
            )
        total = len(tasks)
        results = []
        for i, coro in enumerate(asyncio.as_completed(tasks), start=1):
            results.append(await coro)
            context.log.info("Enriched property %d / %d.", i, total)
        return results

    final_properties = asyncio.run(_run_all())

    result = []
    for fp in final_properties:
        sqm = (
            _parse_display_size(fp.display_size)
            if fp.display_size
            else fp.extracted_sqm
        )
        if sqm is None or sqm >= config.min_square_meters:
            result.append(fp)

    logger.info(
        "%d / %d propert(ies) remain after floor plan size filtering.",
        len(result),
        len(final_properties),
    )
    return result
