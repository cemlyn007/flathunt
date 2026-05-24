import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import dagster as dg

from flathunt.defs.notification.email import (
    NOTIFIED_IDS_DB,
    build_html_email,
    load_notified_ids,
    property_key,
    save_notified_ids,
    send_email,
)
from flathunt.defs.resources import CacheResource, SmtpResource
from flathunt.models import FinalProperty

logger = logging.getLogger(__name__)

_SEARCH_MATCHES_DB = "rightmove_search_matches.db"


@dg.asset(group_name="notification")
def notified_properties(
    context: dg.AssetExecutionContext,
    cache: CacheResource,
    smtp: SmtpResource,
    matched_properties: list[FinalProperty],
) -> None:
    if not smtp.to_addresses:
        context.log.warning("smtp.to_addresses is empty — skipping email notification.")
        context.add_output_metadata({
            "total_count": len(matched_properties),
            "already_notified_count": 0,
            "new_count": 0,
        })
        return

    db_path = Path(cache.data_dir) / NOTIFIED_IDS_DB
    already_notified = load_notified_ids(db_path)

    new_properties = [
        p for p in matched_properties if property_key(p) not in already_notified
    ]
    context.log.info(
        "%d rightmove properties, %d already notified, %d new.",
        len(matched_properties),
        len(already_notified),
        len(new_properties),
    )

    if not new_properties:
        context.log.info("No new properties to notify about. Skipping email.")
        context.add_output_metadata({
            "total_count": len(matched_properties),
            "already_notified_count": len(already_notified),
            "new_count": 0,
        })
        return

    n = len(new_properties)
    plural = "y" if n == 1 else "ies"
    subject = f"Flathunt: {n} new propert{plural}"
    html_body = build_html_email(new_properties)

    send_email(smtp, subject, html_body)
    context.log.info("Email sent to %s.", ", ".join(smtp.to_addresses))

    save_notified_ids(db_path, [property_key(p) for p in new_properties])
    context.log.info("Recorded %d new IDs in %s.", len(new_properties), db_path)

    # Record all matched IDs (not just new ones) for pipeline comparison
    rightmove_ids = [str(p.id) for p in matched_properties if p.source == "rightmove"]
    if rightmove_ids:
        now = int(datetime.now(tz=UTC).timestamp())
        search_db_path = Path(cache.data_dir) / _SEARCH_MATCHES_DB
        search_db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(search_db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS search_matches ("
                "  property_id TEXT PRIMARY KEY,"
                "  found_at INTEGER NOT NULL"
                ")"
            )
            conn.executemany(
                "INSERT OR IGNORE INTO search_matches (property_id, found_at) VALUES (?, ?)",
                [(pid, now) for pid in rightmove_ids],
            )

    context.add_output_metadata({
        "total_count": len(matched_properties),
        "already_notified_count": len(already_notified),
        "new_count": len(new_properties),
    })
