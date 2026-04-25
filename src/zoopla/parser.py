import email
import email.policy
import email.utils
import logging
import re
from datetime import UTC

from bs4 import BeautifulSoup

from zoopla.models import AlertType, ZooplaProperty, ZooplaPropertyAlert

logger = logging.getLogger(__name__)

_CARD_STYLE = re.compile(
    r"border-left.*border-top.*border-right.*border-radius.*8px 8px 0px 0px"
)
_LISTING_URL = re.compile(r"zoopla\.co\.uk/(?:for-sale|new-homes)/details/\d+")
_LISTING_ID = re.compile(r"/details/(\d+)/")
_PRICE_AMOUNT = re.compile(r"£([\d,]+)")
_AGENT_LOGO = re.compile(r"agent_logo")
_PHONE_HREF = re.compile(r"^tel:")


def _parse_price(text: str) -> int | None:
    match = _PRICE_AMOUNT.search(text)
    if match:
        return int(match.group(1).replace(",", ""))
    return None


def _extract_listing_id(url: str) -> str | None:
    match = _LISTING_ID.search(url)
    return match.group(1) if match else None


def parse_zoopla_alert_html(html: str) -> list[ZooplaProperty]:
    soup = BeautifulSoup(html, "html.parser")
    listing_tds = soup.find_all("td", style=_CARD_STYLE)

    properties: list[ZooplaProperty] = []
    for td in listing_tds:
        listing_id: str | None = None
        url: str | None = None
        image_url: str | None = None
        price_gbp: int | None = None
        price_text: str = ""
        reduction_gbp: int | None = None
        reduction_text: str | None = None
        property_type: str | None = None
        address: str | None = None
        agent_logo_url: str | None = None
        agent_phone: str | None = None

        img_link = td.find("a", href=_LISTING_URL)
        if img_link:
            href_value = img_link.get("href")
            # href is a single-valued attribute, should be str | None
            if isinstance(href_value, str):
                url = href_value.split("?")[0]
                listing_id = _extract_listing_id(href_value)
            img = img_link.find("img")
            if img:
                src_value = img.get("src")
                # src is a single-valued attribute, should be str | None
                if isinstance(src_value, str):
                    image_url = src_value

        h3 = td.find("h3")
        if h3:
            price_text = h3.get_text(strip=True)
            price_gbp = _parse_price(price_text)

        for p in td.find_all("p"):
            text = p.get_text(strip=True)
            if "Reduced by" in text:
                reduction_text = text
                reduction_gbp = _parse_price(text)
            elif "for sale" in text or "to rent" in text:
                strong = p.find("strong")
                if strong:
                    property_type = strong.get_text(strip=True)
                span = p.find("span")
                if span:
                    address = span.get_text(strip=True)

        parent_tr = td.find_parent("tr")
        if parent_tr:
            next_tr = parent_tr.find_next_sibling("tr")
            if next_tr:
                agent_img = next_tr.find("img", src=_AGENT_LOGO)
                if agent_img:
                    agent_src_value = agent_img.get("src")
                    # src is a single-valued attribute, should be str | None
                    if isinstance(agent_src_value, str):
                        agent_logo_url = agent_src_value
                phone_link = next_tr.find("a", href=_PHONE_HREF)
                if phone_link:
                    phone_text = phone_link.get_text(strip=True)
                    agent_phone = phone_text or None

        if listing_id is None or url is None:
            logger.warning("Skipping listing card with missing id or url")
            continue

        properties.append(
            ZooplaProperty(
                listing_id=listing_id,
                url=url,
                image_url=image_url,
                price_gbp=price_gbp,
                price_text=price_text,
                reduction_gbp=reduction_gbp,
                reduction_text=reduction_text,
                property_type=property_type,
                address=address,
                agent_logo_url=agent_logo_url,
                agent_phone=agent_phone,
            )
        )

    return properties


def parse_zoopla_alert_email(raw_bytes: bytes) -> ZooplaPropertyAlert:
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

    alert_type = (
        AlertType.PRICE_REDUCED if "Price reduced" in subject else AlertType.NEW_LISTING
    )

    html_content: str | None = None
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            html_content = part.get_content()
            break

    if html_content is None:
        raise ValueError("No HTML part found in email")

    properties = parse_zoopla_alert_html(html_content)

    return ZooplaPropertyAlert(
        message_id=message_id.strip(),
        subject=subject,
        received_at=received_at,
        alert_type=alert_type,
        properties=properties,
    )
