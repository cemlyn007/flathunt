import html
import logging
import os
import smtplib
import sqlite3
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import dagster as dg
from pydantic import Field

import rightmove
from flathunt.defs.enriched_properties import _parse_display_size
from flathunt.models import FinalProperty

logger = logging.getLogger(__name__)

_NOTIFIED_IDS_DB = "notified_properties.db"


class Config(dg.Config):
    cache_data_dir: str = "cache"
    smtp_to_addresses: list[str] = Field(default_factory=list)
    smtp_host: str = Field(default_factory=lambda: os.environ["FLATHUNT__SMTP_HOST"])
    smtp_port: int = Field(
        default_factory=lambda: int(os.environ.get("FLATHUNT__SMTP_PORT", "587"))
    )
    smtp_username: str = Field(
        default_factory=lambda: os.environ["FLATHUNT__SMTP_USERNAME"]
    )
    smtp_password: str = Field(
        default_factory=lambda: os.environ["FLATHUNT__SMTP_PASSWORD"]
    )
    smtp_from_address: str = Field(
        default_factory=lambda: os.environ["FLATHUNT__SMTP_FROM"]
    )


def _open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS notified ("
        "  property_id INTEGER PRIMARY KEY,"
        "  notified_at INTEGER NOT NULL"
        ")"
    )
    conn.commit()
    return conn


def _load_notified_ids(path: Path) -> set[int]:
    with _open_db(path) as conn:
        rows = conn.execute("SELECT property_id FROM notified").fetchall()
    return {row[0] for row in rows}


def _save_notified_ids(path: Path, ids: list[int]) -> None:
    now = int(datetime.now(tz=timezone.utc).timestamp())
    with _open_db(path) as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO notified (property_id, notified_at) VALUES (?, ?)",
            [(pid, now) for pid in ids],
        )


def _format_size(prop: FinalProperty) -> str:
    sqm = (
        _parse_display_size(prop.display_size)
        if prop.display_size
        else prop.extracted_sqm
    )
    if sqm is not None:
        return f"{sqm:.0f} sqm"
    return "—"


def _format_price(prop: FinalProperty) -> str:
    if prop.price and prop.price.amount:
        return f"£{prop.price.amount:,}"
    return "—"


def _format_max_commute(prop: FinalProperty) -> str:
    durations = [d for d in prop.commute_durations if d is not None]
    if not durations:
        return "—"
    return f"{max(durations)} mins"


def _format_council_tax(prop: FinalProperty) -> str:
    band = prop.council_tax_band or prop.extracted_council_tax_band
    return html.escape(f"Band {band}") if band else "—"


def _format_tenure(prop: FinalProperty) -> str:
    tenure = prop.tenure_type or prop.extracted_tenure_type
    lease = prop.years_remaining_on_lease or prop.extracted_years_remaining_on_lease
    if not tenure:
        return "—"
    label = html.escape(tenure)
    if lease is not None:
        label += f" ({lease:,} yrs)"
    return label


def _property_card(prop: FinalProperty, index: int) -> str:
    address = html.escape(prop.display_address)
    price = _format_price(prop)
    beds = str(prop.bedrooms) if prop.bedrooms is not None else "—"
    baths = str(prop.bathrooms) if prop.bathrooms is not None else "—"
    size = _format_size(prop)
    commute = _format_max_commute(prop)
    council_tax = _format_council_tax(prop)
    tenure = _format_tenure(prop)

    view_button = ""
    if prop.property_url:
        url = html.escape(rightmove.api.property_url(prop.property_url))
        view_button = (
            f'<a href="{url}" style="display: inline-block; margin-top: 16px; '
            f"padding: 10px 20px; background-color: #00aeef; color: #ffffff; "
            f"text-decoration: none; border-radius: 4px; font-weight: bold; "
            f'font-size: 14px;">View on Rightmove &rarr;</a>'
        )

    stat_style = (
        "display: inline-block; margin: 4px 8px 4px 0; padding: 4px 10px; "
        "background: #f0f0f0; border-radius: 3px; font-size: 13px; color: #555;"
    )

    stats = "".join(
        f'<span style="{stat_style}">{label}</span>'
        for label in [
            f"&#127968; {beds} bed",
            f"&#128703; {baths} bath",
            f"&#9634; {size}",
            f"&#128651; {commute}",
            f"&#127981; {council_tax}",
            f"&#128196; {tenure}",
        ]
    )

    border_color = "#00aeef" if index % 2 == 0 else "#e05c5c"
    return (
        f'<div style="border: 1px solid #e0e0e0; border-left: 4px solid {border_color}; '
        f"border-radius: 4px; padding: 20px 24px; margin-bottom: 16px; "
        f'background: #ffffff; font-family: sans-serif;">'
        f'<div style="font-size: 18px; font-weight: bold; color: #222; margin-bottom: 4px;">'
        f"{address}</div>"
        f'<div style="font-size: 22px; font-weight: bold; color: #00aeef; margin-bottom: 12px;">'
        f"{price}</div>"
        f'<div style="margin-bottom: 4px;">{stats}</div>'
        f"{view_button}"
        f"</div>"
    )


def _build_html_email(new_properties: list[FinalProperty]) -> str:
    n = len(new_properties)
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    plural = "y" if n == 1 else "ies"

    cards = "\n".join(_property_card(p, i) for i, p in enumerate(new_properties))

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin: 0; padding: 0; background-color: #f5f5f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
  <div style="max-width: 640px; margin: 0 auto; padding: 24px 16px;">

    <!-- Header -->
    <div style="background: linear-gradient(135deg, #1a1a4e 0%, #00aeef 100%); border-radius: 8px; padding: 28px 32px; margin-bottom: 24px; color: white;">
      <div style="font-size: 13px; text-transform: uppercase; letter-spacing: 1px; opacity: 0.8; margin-bottom: 8px;">Flathunt Alert</div>
      <div style="font-size: 28px; font-weight: bold; margin-bottom: 4px;">{n} new propert{plural} found</div>
      <div style="font-size: 13px; opacity: 0.7;">{now}</div>
    </div>

    <!-- Property cards -->
    {cards}

    <!-- Footer -->
    <div style="text-align: center; padding: 16px; color: #aaa; font-size: 12px;">
      Sent by Flathunt &bull; <a href="https://www.rightmove.co.uk" style="color: #aaa;">rightmove.co.uk</a>
    </div>

  </div>
</body>
</html>"""


def _send_email(config: Config, subject: str, html_body: str) -> None:
    to = ", ".join(config.smtp_to_addresses)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.smtp_from_address
    msg["To"] = to
    msg.set_content("See the HTML version of this email for property details.")
    msg.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.login(config.smtp_username, config.smtp_password)
        server.send_message(msg)


@dg.asset
def notified_properties(
    context: dg.AssetExecutionContext,
    config: Config,
    enriched_properties: list[FinalProperty],
) -> None:
    """Send email notifications for newly seen enriched properties.

    Loads the set of already-notified property IDs from a JSON file, computes
    the diff against the current enriched_properties list, and if any new
    properties exist sends an HTML summary email via SMTP. Updates the
    persistent ID set only after a successful send so that failures are
    automatically retried on the next pipeline run.

    Args:
        config: SMTP credentials, recipient list, and cache directory path.
        enriched_properties: Fully enriched properties from the enriched_properties asset.
    """
    if not config.smtp_to_addresses:
        context.log.warning("smtp_to_addresses is empty — skipping email notification.")
        return

    db_path = Path(config.cache_data_dir) / _NOTIFIED_IDS_DB
    already_notified = _load_notified_ids(db_path)

    new_properties = [p for p in enriched_properties if p.id not in already_notified]
    context.log.info(
        "%d total properties, %d already notified, %d new.",
        len(enriched_properties),
        len(already_notified),
        len(new_properties),
    )

    if not new_properties:
        context.log.info("No new properties to notify about. Skipping email.")
        return

    n = len(new_properties)
    plural = "y" if n == 1 else "ies"
    subject = f"Flathunt: {n} new propert{plural}"
    html_body = _build_html_email(new_properties)

    _send_email(config, subject, html_body)
    context.log.info("Email sent to %s.", ", ".join(config.smtp_to_addresses))

    _save_notified_ids(db_path, [p.id for p in new_properties])
    context.log.info("Recorded %d new IDs in %s.", len(new_properties), db_path)
