import json
import logging
from datetime import UTC, datetime

import dagster as dg

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
    message_id: str = ""


@dg.asset(group_name="rightmove")
def rightmove_property_alerts(
    context: dg.AssetExecutionContext,
    config: RightmoveAlertsConfig,
    imap: ImapResource,
) -> RightmovePropertyAlert:
    if not config.message_id:
        context.log.info("No message_id provided; returning empty alert.")
        context.add_output_metadata({"property_count": 0})
        return RightmovePropertyAlert(
            message_id="",
            subject="",
            received_at=datetime.now(tz=UTC),
            properties=[],
        )
    with RightmoveImapChecker(
        imap.host, imap.port, imap.username, imap.password, imap.mailbox
    ) as checker:
        raw_email = checker.fetch_by_message_id(config.message_id)
    alert = parse_rightmove_alert_email(raw_email.raw_bytes)
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
    context.add_output_metadata({"property_count": len(alert.properties)})
    return alert


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

    with RightmoveImapChecker(
        imap.host, imap.port, imap.username, imap.password, imap.mailbox
    ) as checker:
        raw_emails = checker.fetch_unseen_alerts()
        new_uids: list[str] = []

        for raw_email in raw_emails:
            if raw_email.message_id in seen_message_ids:
                continue

            run_requests.append(
                dg.RunRequest(
                    run_key=raw_email.message_id,
                    run_config=dg.RunConfig(
                        ops={
                            "rightmove_property_alerts": RightmoveAlertsConfig(
                                message_id=raw_email.message_id
                            )
                        }
                    ),
                    tags={"rightmove/message_id": raw_email.message_id},
                )
            )
            seen_message_ids.add(raw_email.message_id)
            new_uids.append(raw_email.uid)
            context.log.info("Queued run for email %r.", raw_email.message_id)

        if new_uids:
            checker.mark_seen(new_uids)
            context.log.info("Marked %d email(s) as seen in IMAP.", len(new_uids))

    cursor["seen_message_ids"] = list(seen_message_ids)[-500:]
    return dg.SensorResult(run_requests=run_requests, cursor=json.dumps(cursor))
