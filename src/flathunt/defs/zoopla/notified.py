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

__all__ = ["zoopla_notified_properties"]


@dg.asset(group_name="notification")
def zoopla_notified_properties(
    context: dg.AssetExecutionContext,
    cache: CacheResource,
    smtp: SmtpResource,
    zoopla_matched_properties: list[FinalProperty],
) -> None:
    if not zoopla_matched_properties:
        context.log.info("No Zoopla properties after filtering — skipping email.")
        context.add_output_metadata({
            "total_count": 0,
            "already_notified_count": 0,
            "new_count": 0,
        })
        return

    if not smtp.to_addresses:
        context.log.warning("smtp.to_addresses is empty — skipping email notification.")
        context.add_output_metadata({
            "total_count": len(zoopla_matched_properties),
            "already_notified_count": 0,
            "new_count": 0,
        })
        return

    db_path = Path(cache.data_dir) / NOTIFIED_IDS_DB
    already_notified = load_notified_ids(db_path)

    new_properties = [
        p for p in zoopla_matched_properties if property_key(p) not in already_notified
    ]
    context.log.info(
        "%d zoopla matched, %d already notified, %d new.",
        len(zoopla_matched_properties),
        len(already_notified),
        len(new_properties),
    )

    if not new_properties:
        context.log.info("All Zoopla properties already notified — skipping email.")
        context.add_output_metadata({
            "total_count": len(zoopla_matched_properties),
            "already_notified_count": len(already_notified),
            "new_count": 0,
        })
        return

    n = len(new_properties)
    plural = "y" if n == 1 else "ies"
    subject = f"Flathunt (Zoopla): {n} new propert{plural}"
    html_body = build_html_email(new_properties)

    send_email(smtp, subject, html_body)
    context.log.info("Email sent to %s.", ", ".join(smtp.to_addresses))

    save_notified_ids(db_path, [property_key(p) for p in new_properties])
    context.log.info("Recorded %d new Zoopla IDs in %s.", len(new_properties), db_path)
    context.add_output_metadata({
        "total_count": len(zoopla_matched_properties),
        "already_notified_count": len(already_notified),
        "new_count": len(new_properties),
    })
