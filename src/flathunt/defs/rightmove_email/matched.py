import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import dagster as dg

from flathunt.anthropic_extraction import ExtractedAttributes
from flathunt.defs.resources import CacheResource, SearchCriteriaResource
from flathunt.models import FinalProperty, MatchedProperty, parse_display_size_sqm

logger = logging.getLogger(__name__)

__all__ = ["rightmove_email_matched_properties"]

_EMAIL_MATCHES_DB = "rightmove_email_matches.db"


def _open_matches_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS email_matches ("
        "  property_id TEXT PRIMARY KEY,"
        "  found_at INTEGER NOT NULL"
        ")"
    )
    conn.commit()
    return conn


def _record_matched_ids(path: Path, ids: list[str]) -> None:
    now = int(datetime.now(tz=UTC).timestamp())
    with _open_matches_db(path) as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO email_matches (property_id, found_at) VALUES (?, ?)",
            [(pid, now) for pid in ids],
        )


def _merge(
    prop: FinalProperty,
    attrs: ExtractedAttributes,
    commute_durations: list[int | None],
) -> FinalProperty:
    """Merge extracted attributes and commute durations into a candidate FinalProperty."""
    desc = attrs.description
    fp = attrs.floor_plan
    updates: dict = {
        "commute_durations": list(commute_durations),
        "extracted_sqm": fp.total_sqm if fp else None,
        "extracted_sqm_breakdown": fp.breakdown_csv if fp else None,
        "extracted_tenure_type": desc.tenure_type if desc else None,
        "extracted_years_remaining_on_lease": desc.years_remaining_on_lease
        if desc
        else None,
        "extracted_annual_service_charge": desc.annual_service_charge if desc else None,
        "extracted_annual_ground_rent": desc.annual_ground_rent if desc else None,
        "extracted_council_tax_band": desc.council_tax_band if desc else None,
    }
    if prop.bedrooms is None and desc and desc.bedrooms is not None:
        updates["bedrooms"] = desc.bedrooms
    if prop.bathrooms is None and desc and desc.bathrooms is not None:
        updates["bathrooms"] = desc.bathrooms
    return prop.model_copy(update=updates)


@dg.asset(group_name="rightmove_email")
def rightmove_email_matched_properties(
    context: dg.AssetExecutionContext,
    search_criteria: SearchCriteriaResource,
    cache: CacheResource,
    rightmove_email_matched_ids: list[MatchedProperty],
    rightmove_email_candidate_properties: list[FinalProperty],
    rightmove_email_extracted_attributes: dict[str, ExtractedAttributes],
) -> list[FinalProperty]:
    """Merge ExtractedAttributes into candidate FinalProperty objects and apply size filter.

    All cheap filters (price, photos, isochrone) and the commute filter have
    already been applied upstream.  This asset merges vision/LLM-extracted
    attributes into the surviving candidates, applies a null-safe size filter,
    then records matched IDs in the matches DB.

    Args:
        context: Dagster execution context.
        search_criteria: Minimum floor area threshold.
        cache: Cache resource providing the data directory path.
        rightmove_email_matched_ids: Listings that passed all upstream filters,
            paired with per-destination commute durations.
        rightmove_email_candidate_properties: Enriched FinalProperty objects for
            candidates (with extracted_sqm=None; display_size may be set).
        rightmove_email_extracted_attributes: Vision/LLM-extracted attributes
            keyed by listing_id (string).

    Returns:
        Final properties ready for notification.
    """
    prop_by_id = {p.id: p for p in rightmove_email_candidate_properties}

    merged: list[FinalProperty] = []
    for matched in rightmove_email_matched_ids:
        prop = prop_by_id.get(matched.property_id)
        if prop is None:
            context.log.warning(
                "Matched property_id %s not found in candidates; skipping.",
                matched.property_id,
            )
            continue
        attrs = rightmove_email_extracted_attributes.get(
            str(matched.property_id), ExtractedAttributes()
        )
        merged.append(_merge(prop, attrs, matched.commute_durations))

    # Null-safe size filter: display_size takes precedence over extracted_sqm.
    # Unknown size (both None) → KEPT, consistent with prior behaviour.
    size_passed: list[FinalProperty] = []
    for fp in merged:
        sqm = (
            parse_display_size_sqm(fp.display_size)
            if fp.display_size
            else fp.extracted_sqm
        )
        if sqm is None or sqm >= search_criteria.min_square_meters:
            size_passed.append(fp)
        else:
            context.log.info(
                "Property %s floor area %.1f sqm below minimum %.1f; excluding.",
                fp.id,
                sqm,
                search_criteria.min_square_meters,
            )

    db_path = Path(cache.data_dir) / _EMAIL_MATCHES_DB
    _record_matched_ids(db_path, [str(p.id) for p in size_passed])

    context.add_output_metadata({
        "matched_count": len(rightmove_email_matched_ids),
        "final_count": len(size_passed),
    })
    return size_passed
