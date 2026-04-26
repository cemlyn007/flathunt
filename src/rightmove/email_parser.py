import email
import email.policy
import email.utils
import logging
import re
from datetime import UTC

from bs4 import BeautifulSoup, Tag

from rightmove.email_models import RightmoveProperty, RightmovePropertyAlert

logger = logging.getLogger(__name__)

__all__ = ["parse_rightmove_alert_email", "parse_rightmove_alert_html"]

_LISTING_ID = re.compile(r"/properties/(\d+)")
_PRICE_AMOUNT = re.compile(r"£([\d,]+)")


def _parse_price(text: str) -> int | None:
    match = _PRICE_AMOUNT.search(text)
    if match:
        return int(match.group(1).replace(",", ""))
    return None


def _extract_listing_id(url: str) -> str | None:
    match = _LISTING_ID.search(url)
    return match.group(1) if match else None


def _str_attr(tag: Tag, attr: str) -> str | None:
    value = tag.get(attr)
    return value if isinstance(value, str) else None


def parse_rightmove_alert_html(html: str) -> list[RightmoveProperty]:
    soup = BeautifulSoup(html, "html.parser")

    all_cards = soup.find_all("td", class_=["sm-px-0", "sm-w-full", "sm-inline-block"])
    cards = [c for c in all_cards if "width: 50%" in (c.get("style") or "")]

    properties: list[RightmoveProperty] = []
    for card in cards:
        prop_link = next(
            (
                a
                for a in card.find_all("a", href=True)
                if isinstance(a, Tag) and "/properties/" in (a.get("href") or "")
            ),
            None,
        )
        if not isinstance(prop_link, Tag):
            logger.warning("Skipping card with no property link")
            continue

        raw_url = _str_attr(prop_link, "href") or ""
        url = raw_url.split("?")[0]
        listing_id = _extract_listing_id(url)
        if not listing_id:
            logger.warning("Skipping card with no listing id in %r", url)
            continue

        img = card.find("img", alt="image")
        image_url: str | None = _str_attr(img, "src") if isinstance(img, Tag) else None

        price_div = next(
            (
                d
                for d in card.find_all("div")
                if isinstance(d, Tag)
                and d.get_text(strip=True).startswith("£")
                and not d.find("div")
            ),
            None,
        )
        price_text = (
            price_div.get_text(strip=True) if isinstance(price_div, Tag) else ""
        )
        price_gbp = _parse_price(price_text)

        qualifier_div = (
            price_div.find_next_sibling("div") if isinstance(price_div, Tag) else None
        )
        price_qualifier: str | None = (
            qualifier_div.get_text(strip=True) or None
            if isinstance(qualifier_div, Tag)
            else None
        )

        top_bar = card.find("td", attrs={"bgcolor": "#000433"})
        is_reduced = isinstance(top_bar, Tag) and "Reduced" in top_bar.get_text()

        def _icon_count(bar: Tag | None, alt: str) -> int | None:
            icon = bar.find("img", alt=alt) if isinstance(bar, Tag) else None
            if not isinstance(icon, Tag):
                return None
            icon_td = icon.find_parent("td")
            count_td = (
                icon_td.find_next_sibling("td") if isinstance(icon_td, Tag) else None
            )
            text = count_td.get_text(strip=True) if isinstance(count_td, Tag) else ""
            return int(text) if text.isdigit() else None

        photo_count = _icon_count(
            top_bar if isinstance(top_bar, Tag) else None, "photos"
        )
        floorplan_count = _icon_count(
            top_bar if isinstance(top_bar, Tag) else None, "floorplan"
        )

        type_link = next(
            (
                a
                for a in card.find_all("a", href=True)
                if isinstance(a, Tag)
                and ("for sale" in a.get_text() or "to rent" in a.get_text())
            ),
            None,
        )
        property_type: str | None = (
            type_link.get_text(strip=True) if isinstance(type_link, Tag) else None
        )

        address: str | None = None
        marketed_by: str | None = None
        if isinstance(type_link, Tag):
            type_td = type_link.find_parent("td")
            type_tr = type_td.find_parent("tr") if isinstance(type_td, Tag) else None
            addr_tr = (
                type_tr.find_next_sibling("tr") if isinstance(type_tr, Tag) else None
            )
            addr_td = addr_tr.find("td") if isinstance(addr_tr, Tag) else None
            address = addr_td.get_text(strip=True) if isinstance(addr_td, Tag) else None

            marketed_tr = (
                addr_tr.find_next_sibling("tr") if isinstance(addr_tr, Tag) else None
            )
            marketed_td = (
                marketed_tr.find("td") if isinstance(marketed_tr, Tag) else None
            )
            marketed_by = (
                marketed_td.get_text(strip=True)
                if isinstance(marketed_td, Tag)
                else None
            )

        phone_link = next(
            (
                a
                for a in card.find_all("a", href=True)
                if isinstance(a, Tag)
                and isinstance(a.get("href"), str)
                and (_str_attr(a, "href") or "").startswith("tel:")
            ),
            None,
        )
        agent_phone: str | None = None
        if isinstance(phone_link, Tag):
            href = _str_attr(phone_link, "href") or ""
            agent_phone = href[4:].strip() or None

        properties.append(
            RightmoveProperty(
                listing_id=listing_id,
                url=url,
                image_url=image_url,
                price_gbp=price_gbp,
                price_text=price_text,
                price_qualifier=price_qualifier,
                is_reduced=is_reduced,
                property_type=property_type,
                address=address,
                marketed_by=marketed_by,
                agent_phone=agent_phone,
                photo_count=photo_count,
                floorplan_count=floorplan_count,
            )
        )

    return properties


def parse_rightmove_alert_email(raw_bytes: bytes) -> RightmovePropertyAlert:
    msg = email.message_from_bytes(raw_bytes, policy=email.policy.default)

    message_id: str | None = msg.get("Message-ID")
    if not message_id:
        raise ValueError("Email is missing Message-ID header")

    subject: str | None = msg.get("Subject")
    if not subject:
        raise ValueError("Email is missing Subject header")

    date_str: str | None = msg.get("Date")
    if date_str:
        received_at = email.utils.parsedate_to_datetime(date_str)
        if received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=UTC)
        else:
            received_at = received_at.astimezone(UTC)
    else:
        raise ValueError("Email is missing Date header")

    html_content: str | None = None
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            html_content = part.get_content()
            break

    if html_content is None:
        raise ValueError("No HTML part found in email")

    properties = parse_rightmove_alert_html(html_content)

    return RightmovePropertyAlert(
        message_id=message_id.strip(),
        subject=subject,
        received_at=received_at,
        properties=properties,
    )
