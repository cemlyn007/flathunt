import hashlib
import json
import logging
from pathlib import Path

import dagster as dg

from flathunt.defs.resources import CacheResource, ImapResource
from zoopla.imap import ZooplaImapChecker
from zoopla.models import ZooplaPropertyAlert
from zoopla.parser import parse_zoopla_alert_email

logger = logging.getLogger(__name__)

__all__ = [
    "zoopla_alerts_job",
    "zoopla_email_sensor",
    "zoopla_property_alerts",
]

_SENSOR_INTERVAL = 300  # seconds


class ZooplaAlertsConfig(dg.Config):
    eml_path: str


@dg.asset(group_name="zoopla_alerts")
def zoopla_property_alerts(
    context: dg.AssetExecutionContext,
    config: ZooplaAlertsConfig,
) -> ZooplaPropertyAlert:
    raw_bytes = Path(config.eml_path).read_bytes()
    alert = parse_zoopla_alert_email(raw_bytes)
    context.log.info(
        "Parsed %d propert(ies) from alert (type=%s, subject=%r).",
        len(alert.properties),
        alert.alert_type.value,
        alert.subject,
    )
    for prop in alert.properties:
        context.log.info(
            "  %s — %s — £%s",
            prop.listing_id,
            prop.address,
            f"{prop.price_gbp:,}" if prop.price_gbp is not None else "?",
        )
    return alert


zoopla_alerts_job = dg.define_asset_job(
    name="zoopla_alerts",
    selection=dg.AssetSelection.assets(zoopla_property_alerts),
)


@dg.sensor(
    job=zoopla_alerts_job,
    minimum_interval_seconds=_SENSOR_INTERVAL,
    default_status=dg.DefaultSensorStatus.RUNNING,
)
def zoopla_email_sensor(
    context: dg.SensorEvaluationContext,
    imap: ImapResource,
    cache: CacheResource,
) -> dg.SensorResult:
    cursor = json.loads(context.cursor) if context.cursor else {}
    seen_message_ids: set[str] = set(cursor.get("seen_message_ids", []))

    cache_dir = Path(cache.data_dir) / "zoopla_emails"
    cache_dir.mkdir(parents=True, exist_ok=True)

    run_requests: list[dg.RunRequest] = []

    with ZooplaImapChecker(
        imap.host, imap.port, imap.username, imap.password
    ) as checker:
        raw_emails = checker.fetch_unseen_alerts()
        new_uids: list[str] = []

        for raw_email in raw_emails:
            if raw_email.message_id in seen_message_ids:
                continue

            safe_name = hashlib.sha256(raw_email.message_id.encode()).hexdigest()
            eml_path = cache_dir / f"{safe_name}.eml"
            eml_path.write_bytes(raw_email.raw_bytes)

            run_requests.append(
                dg.RunRequest(
                    run_key=raw_email.message_id,
                    run_config=dg.RunConfig(
                        ops={
                            "zoopla_property_alerts": ZooplaAlertsConfig(
                                eml_path=str(eml_path)
                            )
                        }
                    ),
                    tags={"zoopla/message_id": raw_email.message_id},
                )
            )
            seen_message_ids.add(raw_email.message_id)
            new_uids.append(raw_email.uid)
            context.log.info("Queued run for email %r.", raw_email.message_id)

        if new_uids:
            checker.mark_seen(new_uids)
            context.log.info("Marked %d email(s) as seen in IMAP.", len(new_uids))

    cursor["seen_message_ids"] = list(seen_message_ids)
    return dg.SensorResult(run_requests=run_requests, cursor=json.dumps(cursor))
