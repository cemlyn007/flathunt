import html
import smtplib
import sqlite3
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path

import rightmove
from flathunt.defs.resources import SmtpResource
from flathunt.models import FinalProperty, parse_display_size_sqm

NOTIFIED_IDS_DB = "notified_properties.db"


def _open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS notified ("
        "  property_id TEXT PRIMARY KEY,"
        "  notified_at INTEGER NOT NULL"
        ")"
    )
    _migrate_notified_to_text_pk(conn)
    conn.commit()
    return conn


def _migrate_notified_to_text_pk(conn: sqlite3.Connection) -> None:
    """Migrate legacy `notified` table where property_id was INTEGER PRIMARY KEY.

    Why: pre-source-prefix versions stored bare rightmove ids; the new key format is
    "{source}:{id}". Inserting a string into an INTEGER PRIMARY KEY raises
    IntegrityError("datatype mismatch"). Rewrite the table once and prefix existing
    rows with "rightmove:" (the only source the legacy code populated).
    """
    pk_type = next(
        (
            row[2]
            for row in conn.execute("PRAGMA table_info(notified)")
            if row[1] == "property_id"
        ),
        None,
    )
    if pk_type != "INTEGER":
        return
    conn.executescript(
        """
        CREATE TABLE notified_new (
            property_id TEXT PRIMARY KEY,
            notified_at INTEGER NOT NULL
        );
        INSERT INTO notified_new (property_id, notified_at)
            SELECT 'rightmove:' || property_id, notified_at FROM notified;
        DROP TABLE notified;
        ALTER TABLE notified_new RENAME TO notified;
        """
    )


def load_notified_ids(path: Path) -> set[str]:
    with _open_db(path) as conn:
        rows = conn.execute("SELECT property_id FROM notified").fetchall()
    return {row[0] for row in rows}


def save_notified_ids(path: Path, ids: list[str]) -> None:
    now = int(datetime.now(tz=UTC).timestamp())
    with _open_db(path) as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO notified (property_id, notified_at) VALUES (?, ?)",
            [(pid, now) for pid in ids],
        )


def property_key(prop: FinalProperty) -> str:
    return f"{prop.source}:{prop.id}"


def _format_size(prop: FinalProperty) -> str:
    sqm = (
        parse_display_size_sqm(prop.display_size)
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
        if prop.source == "zoopla":
            url = html.escape(prop.property_url)
            label = "View on Zoopla"
        else:
            url = html.escape(rightmove.api.property_url(prop.property_url))
            label = "View on Rightmove"
        view_button = (
            f'<a href="{url}" style="display: inline-block; margin-top: 16px; '
            f"padding: 10px 20px; background-color: #00aeef; color: #ffffff; "
            f"text-decoration: none; border-radius: 4px; font-weight: bold; "
            f'font-size: 14px;">{label} &rarr;</a>'
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


def build_html_email(new_properties: list[FinalProperty]) -> str:
    n = len(new_properties)
    now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
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
      Sent by Flathunt
    </div>

  </div>
</body>
</html>"""


def send_email(smtp: SmtpResource, subject: str, html_body: str) -> None:
    to = ", ".join(smtp.to_addresses)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp.from_address
    msg["To"] = to
    msg.set_content("See the HTML version of this email for property details.")
    msg.add_alternative(html_body, subtype="html")
    with smtplib.SMTP(smtp.host, smtp.port) as server:
        server.ehlo()
        server.starttls()
        server.login(smtp.username, smtp.password)
        server.send_message(msg)
