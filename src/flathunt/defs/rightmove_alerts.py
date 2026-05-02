import hashlib
import json
import logging

import dagster as dg
from pydantic import Field

from flathunt.defs.paths import load_job_run_config
from flathunt.defs.resources import ImapResource
from rightmove.email_models import RightmovePropertyAlert
from rightmove.email_parser import parse_rightmove_alert_email
from rightmove.imap import RightmoveImapChecker

logger = logging.getLogger(__name__)

__all__ = [
    "rightmove_email_sensor",
    "rightmove_property_alerts",
]

_SENSOR_INTERVAL = 300  # seconds


class RightmoveAlertsConfig(dg.Config):
    message_ids: list[str] = Field(default_factory=list)


@dg.asset(group_name="rightmove")
def rightmove_property_alerts(
    context: dg.AssetExecutionContext,
    config: RightmoveAlertsConfig,
    imap: ImapResource,
) -> list[RightmovePropertyAlert]:
    if not config.message_ids:
        context.log.info("No message_ids provided; returning no alerts.")
        context.add_output_metadata({"alert_count": 0, "property_count": 0})
        return []

    alerts: list[RightmovePropertyAlert] = []
    with RightmoveImapChecker(
        imap.host, imap.port, imap.username, imap.password, imap.mailbox
    ) as checker:
        for message_id in config.message_ids:
            raw_email = checker.fetch_by_message_id(message_id)
            alert = parse_rightmove_alert_email(raw_email.raw_bytes)
            alerts.append(alert)
            context.log.info(
                "Parsed %d propert(ies) from alert (subject=%r).",
                len(alert.properties),
                alert.subject,
            )
            for prop in alert.properties:
                context.log.info(
                    "  %s — %s — %s%s",
                    prop.listing_id,
                    prop.address,
                    f"£{prop.price_gbp:,}" if prop.price_gbp is not None else "?",
                    " [REDUCED]" if prop.is_reduced else "",
                )

    total_properties = sum(len(a.properties) for a in alerts)
    context.add_output_metadata({
        "alert_count": len(alerts),
        "property_count": total_properties,
    })
    return alerts


@dg.sensor(
    job_name="rightmove_email",
    minimum_interval_seconds=_SENSOR_INTERVAL,
    default_status=dg.DefaultSensorStatus.RUNNING,
)
def rightmove_email_sensor(
    context: dg.SensorEvaluationContext,
    imap: ImapResource,
) -> dg.SensorResult:
    cursor = json.loads(context.cursor) if context.cursor else {}
    seen_message_ids: set[str] = set(cursor.get("seen_message_ids", []))

    run_requests: list[dg.RunRequest] = []
    batch_message_ids: list[str] = []

    with RightmoveImapChecker(
        imap.host, imap.port, imap.username, imap.password, imap.mailbox
    ) as checker:
        raw_emails = checker.fetch_unseen_alerts()
        new_uids: list[str] = []

        for raw_email in raw_emails:
            if raw_email.message_id in seen_message_ids:
                continue
            batch_message_ids.append(raw_email.message_id)
            seen_message_ids.add(raw_email.message_id)
            new_uids.append(raw_email.uid)
            context.log.info("Batched email %r.", raw_email.message_id)

        if batch_message_ids:
            run_key = hashlib.sha256(
                "|".join(sorted(batch_message_ids)).encode()
            ).hexdigest()
            run_config = load_job_run_config("rightmove_run_config.yaml")
            run_config.setdefault("ops", {})["rightmove_property_alerts"] = {
                "config": {"message_ids": batch_message_ids}
            }
            run_requests.append(
                dg.RunRequest(
                    run_key=run_key,
                    run_config=run_config,
                    tags={"rightmove/batch_size": str(len(batch_message_ids))},
                )
            )
            context.log.info(
                "Queued single run for %d email(s).", len(batch_message_ids)
            )

        if new_uids:
            checker.mark_seen(new_uids)
            context.log.info("Marked %d email(s) as seen in IMAP.", len(new_uids))

    cursor["seen_message_ids"] = list(seen_message_ids)[-500:]
    return dg.SensorResult(run_requests=run_requests, cursor=json.dumps(cursor))
