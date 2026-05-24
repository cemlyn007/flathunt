import contextlib
import email
import email.policy
import email.utils
import json
import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from bs4 import BeautifulSoup

from zoopla.models import (
    AlertType,
    ZooplaListingDetail,
    ZooplaProperty,
    ZooplaPropertyAlert,
)

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


_ANALYTICS_TAXONOMY = re.compile(
    r'\{"__typename":"ListingAnalyticsTaxonomy"[^<]+\}', re.DOTALL
)
_FLOOR_AREA_SQFT = re.compile(r"([\d,]+)\s*sq\.\s*ft")
_RSC_PUSH = re.compile(r'^self\.__next_f\.push\(\[1,"(.+)"\]\s*\)\s*;?\s*$', re.DOTALL)
_FLOORPLAN_HOST = "https://lc.zoocdn.com/"


def _rsc_buffer(soup: BeautifulSoup) -> str:
    """Concatenate every ``self.__next_f.push([1, "..."])`` payload into one string."""
    parts: list[str] = []
    for sc in soup.find_all("script"):
        text = (sc.string or "").strip()
        m = _RSC_PUSH.match(text)
        if not m:
            continue
        with contextlib.suppress(json.JSONDecodeError):
            parts.append(json.loads(f'"{m.group(1)}"'))
    return "".join(parts)


def _iter_json_values(buf: str) -> Iterator[Any]:
    """Yield each well-formed JSON value embedded in an RSC buffer.

    The buffer mixes JSON objects/arrays with non-JSON RSC directives
    (e.g. ``T<n>,...`` text segments).  Probing each ``{`` and ``[`` with
    ``raw_decode`` cleanly skips those directives.
    """
    decoder = json.JSONDecoder()
    i = 0
    n = len(buf)
    while i < n:
        c = buf[i]
        if c in "{[":
            try:
                value, end = decoder.raw_decode(buf, i)
            except json.JSONDecodeError:
                i += 1
                continue
            yield value
            i = end
        else:
            i += 1


def _walk(node: Any) -> Iterator[tuple[str, Any]]:
    """Yield every ``(key, value)`` pair anywhere in a JSON tree."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def parse_zoopla_listing_html(html: str, url: str) -> ZooplaListingDetail:
    soup = BeautifulSoup(html, "html.parser")

    listing_id = _extract_listing_id(url) or ""

    taxonomy = _parse_taxonomy(soup)
    listing_ld = _parse_real_estate_ld(soup)
    property_type, address = _parse_h1(soup)
    key_features = _parse_key_features(soup)
    description = _parse_description(soup)
    more_info = _parse_more_info(soup)
    latitude, longitude = _parse_coordinates(soup)
    image_urls = _parse_image_urls(soup, listing_ld, listing_id)
    floorplan_urls = _parse_floorplan_urls(soup)

    price_gbp: int | None = None
    raw_price = taxonomy.get("price_actual")
    if raw_price:
        with contextlib.suppress(ValueError):
            price_gbp = int(raw_price)
    if price_gbp is None:
        offers = listing_ld.get("offers", {})
        price_gbp = offers.get("price")

    def _int_or_none(val: str | None) -> int | None:
        try:
            return int(val) if val else None
        except ValueError:
            return None

    def _bool_or_none(val: str | None) -> bool | None:
        if val is None:
            return None
        return val.lower() == "true"

    floor_area_sqft: int | None = _int_or_none(taxonomy.get("size_sq_feet"))
    if floor_area_sqft is None:
        for prop in listing_ld.get("additionalProperty", []):
            if prop.get("name") == "Floor size":
                m = _FLOOR_AREA_SQFT.search(prop.get("value", ""))
                if m:
                    floor_area_sqft = int(m.group(1).replace(",", ""))

    date_posted: datetime | None = None
    date_str = listing_ld.get("datePosted")
    if date_str:
        with contextlib.suppress(ValueError):
            date_posted = datetime.fromisoformat(date_str).replace(tzinfo=UTC)

    return ZooplaListingDetail(
        listing_id=listing_id or taxonomy.get("listing_id", ""),
        url=url,
        price_gbp=price_gbp,
        price_qualifier=taxonomy.get("price_qualifier") or None,
        address=address or taxonomy.get("display_address"),
        property_type=property_type,
        bedrooms=_int_or_none(taxonomy.get("num_beds")),
        bathrooms=_int_or_none(taxonomy.get("num_baths")),
        receptions=_int_or_none(taxonomy.get("num_recepts")),
        floor_area_sqft=floor_area_sqft,
        tenure=more_info.get("Tenure") or taxonomy.get("tenure"),
        service_charge=more_info.get("Service charge"),
        council_tax_band=more_info.get("Council tax band"),
        ground_rent=more_info.get("Ground rent"),
        ground_rent_review_date=more_info.get("Ground rent date of next review"),
        chain_free=_bool_or_none(taxonomy.get("chain_free")),
        listing_condition=taxonomy.get("listing_condition") or None,
        description=description,
        key_features=key_features,
        agent_name=taxonomy.get("branch_name"),
        agent_logo_url=taxonomy.get("branch_logo_url"),
        image_urls=image_urls,
        floorplan_urls=floorplan_urls,
        date_posted=date_posted,
        latitude=latitude,
        longitude=longitude,
    )


def _parse_taxonomy(soup: BeautifulSoup) -> dict:
    for sc in soup.find_all("script"):
        text = sc.string or ""
        m = _ANALYTICS_TAXONOMY.search(text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                logger.warning("Failed to parse ListingAnalyticsTaxonomy JSON")
    return {}


def _parse_real_estate_ld(soup: BeautifulSoup) -> dict:
    for sc in soup.find_all("script", type="application/ld+json"):
        try:
            blob = json.loads(sc.string or "")
        except json.JSONDecodeError:
            continue
        if blob.get("@type") == "RealEstateListing":
            return blob
    return {}


def _parse_h1(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    h1 = soup.find("h1")
    if not h1:
        return None, None
    address_el = h1.find("address")
    address = address_el.get_text(strip=True) if address_el else None
    if address_el:
        address_el.extract()
    property_type = h1.get_text(strip=True) or None
    return property_type, address


def _parse_key_features(soup: BeautifulSoup) -> list[str]:
    section = soup.find("section", {"aria-labelledby": "about"})
    if not section:
        return []
    features = []
    for li in section.find_all("li"):
        spans = li.find_all("span")
        # last span holds the feature text; skip SVG-only items
        text_spans = [s.get_text(strip=True) for s in spans if s.get_text(strip=True)]
        if text_spans:
            features.append(text_spans[-1])
    return features


def _parse_description(soup: BeautifulSoup) -> str | None:
    el = soup.find(class_=re.compile(r"DetailedDescription_detailedDescriptionText"))
    return el.get_text(separator="\n", strip=True) if el else None


def _parse_more_info(soup: BeautifulSoup) -> dict[str, str]:
    section = soup.find("section", {"aria-labelledby": "more-info"})
    if not section:
        return {}
    result: dict[str, str] = {}
    for li in section.find_all("li"):
        label_el = li.find("p", class_=re.compile(r"NtsInfo_ntsInfoItemTitle"))
        value_wrapper = li.find(
            "div", class_=re.compile(r"NtsInfo_ntsInfoItemTextWrapper")
        )
        if not label_el or not value_wrapper:
            continue
        value_el = value_wrapper.find("p")
        if value_el:
            result[label_el.get_text(strip=True)] = value_el.get_text(strip=True)
    return result


_IMAGE_URL_TEMPLATE = "https://lid.zoocdn.com/u/1024/768/{filename}"


def _find_image_galleries(node: Any) -> Iterator[tuple[str | None, list[str]]]:
    """Yield ``(listing_id, filenames)`` for each photo gallery in an RSC tree.

    Zoopla emits the gallery as a ``propertyImage`` array of
    ``{"caption": ..., "filename": ...}`` objects (filenames only, no host) on the
    listing-detail object, which also carries the ``listingId``.  Other
    ``propertyImage`` values on the page are scalar RSC references or single hero
    URLs and are ignored.
    """
    if isinstance(node, dict):
        gallery = node.get("propertyImage")
        if (
            isinstance(gallery, list)
            and gallery
            and all(isinstance(item, dict) and "filename" in item for item in gallery)
        ):
            listing_id = node.get("listingId")
            yield (
                str(listing_id) if listing_id is not None else None,
                [item["filename"] for item in gallery],
            )
        for value in node.values():
            yield from _find_image_galleries(value)
    elif isinstance(node, list):
        for item in node:
            yield from _find_image_galleries(item)


def _parse_image_urls(
    soup: BeautifulSoup, listing_ld: dict, listing_id: str
) -> list[str]:
    """Extract the listing's photo gallery from the RSC ``propertyImage`` array.

    Prefers the gallery whose ``listingId`` matches this listing, so any
    "similar properties" galleries elsewhere on the page are ignored.  Falls back
    to the single JSON-LD hero image when no gallery is found.
    """
    galleries = [
        gallery
        for value in _iter_json_values(_rsc_buffer(soup))
        for gallery in _find_image_galleries(value)
    ]

    filenames: list[str] | None = None
    for gallery_listing_id, gallery_filenames in galleries:
        if gallery_listing_id == listing_id:
            filenames = gallery_filenames
            break
    if filenames is None and len(galleries) == 1:
        filenames = galleries[0][1]

    if filenames:
        return [_IMAGE_URL_TEMPLATE.format(filename=fn) for fn in filenames]

    # Fall back to the single JSON-LD hero image.
    ld_img = listing_ld.get("image")
    return [ld_img] if ld_img else []


def _parse_floorplan_urls(soup: BeautifulSoup) -> list[str]:
    """Extract floor plan image URLs by walking the RSC JSON tree.

    Recognises both shapes Zoopla emits:

    * ``"floorPlan": [{"original": "<url>"}]``
    * ``"floorPlan": {"image": [{"filename": "<hash>.png"}]}``

    String values bound to ``floorPlan`` are RSC reference pointers
    (e.g. ``"$5a:props:..."``) and are ignored by type-checking.
    """
    seen: set[str] = set()
    urls: list[str] = []

    def _add(url: str) -> None:
        if url not in seen:
            seen.add(url)
            urls.append(url)

    buf = _rsc_buffer(soup)
    for top in _iter_json_values(buf):
        for key, value in _walk(top):
            if key != "floorPlan":
                continue
            # Shape 1: list of {"original": "<url>"}
            if isinstance(value, list):
                for entry in value:
                    if isinstance(entry, dict):
                        original = entry.get("original")
                        if isinstance(original, str):
                            _add(original)
            # Shape 2: {"image": [{"filename": "<hash>.png"}]}
            elif isinstance(value, dict):
                images = value.get("image")
                if isinstance(images, list):
                    for entry in images:
                        if isinstance(entry, dict):
                            filename = entry.get("filename")
                            if isinstance(filename, str):
                                _add(_FLOORPLAN_HOST + filename)
            # Anything else (including string RSC reference pointers) is ignored.

    return urls


def _parse_coordinates(soup: BeautifulSoup) -> tuple[float | None, float | None]:
    """Find the listing's lat/lng in the RSC payload.

    The listing's coordinates live in JSON objects keyed by ``uprn``, in two
    shapes Zoopla currently emits:

    * ``{"coordinates": {"latitude": ..., "longitude": ...}, ..., "uprn": ...}``
    * ``{"latitude": ..., "longitude": ..., ..., "uprn": ...}``

    Requiring ``uprn`` filters out the dozens of nearby EV-charging-station
    coordinate objects on the same page.
    """
    buf = _rsc_buffer(soup)
    for top in _iter_json_values(buf):
        for _, value in _walk(top):
            if not isinstance(value, dict) or "uprn" not in value:
                continue
            coords = value.get("coordinates")
            if isinstance(coords, dict):
                lat, lng = coords.get("latitude"), coords.get("longitude")
            else:
                lat, lng = value.get("latitude"), value.get("longitude")
            if lat is None or lng is None:
                continue
            try:
                return float(lat), float(lng)
            except (TypeError, ValueError):
                continue
    return None, None
