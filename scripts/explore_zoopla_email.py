#!/usr/bin/env python3
"""Exploratory script for parsing Zoopla property alert emails."""

import email
import re
import sys
from email import policy
from pathlib import Path

from bs4 import BeautifulSoup


def parse_price(text: str) -> int | None:
    """Parse a price string like 'Guide price £375,000' -> 375000."""
    match = re.search(r"£([\d,]+)", text)
    if match:
        return int(match.group(1).replace(",", ""))
    return None


def extract_zoopla_id(url: str) -> str | None:
    match = re.search(r"/details/(\d+)/", url)
    return match.group(1) if match else None


def parse_zoopla_email(eml_path: Path) -> list[dict]:
    with eml_path.open("rb") as f:
        msg = email.message_from_binary_file(f, policy=policy.default)

    html_part = None
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            html_part = part.get_content()
            break

    if html_part is None:
        print("No HTML part found", file=sys.stderr)
        return []

    soup = BeautifulSoup(html_part, "html.parser")

    # Each listing card is a <td> with this distinctive border-radius pattern
    card_style = re.compile(
        r"border-left.*border-top.*border-right.*border-radius.*8px 8px 0px 0px"
    )
    listing_tds = soup.find_all("td", style=card_style)

    properties = []
    for td in listing_tds:
        prop: dict = {}

        # Property URL + image
        img_link = td.find("a", href=re.compile(r"zoopla\.co\.uk/for-sale/details/\d+"))
        if img_link:
            href = img_link.get("href")
            if isinstance(href, str):
                prop["url"] = href.split("?")[0]
                prop["listing_id"] = extract_zoopla_id(href)
                img = img_link.find("img")
                if img:
                    prop["image_url"] = img.get("src")

        # Price
        h3 = td.find("h3")
        if h3:
            price_text = h3.get_text(strip=True)
            prop["price_text"] = price_text
            prop["price_gbp"] = parse_price(price_text)

        # Reduction + property type/address
        for p in td.find_all("p"):
            text = p.get_text(strip=True)
            if "Reduced by" in text:
                prop["reduction_text"] = text
                prop["reduction_gbp"] = parse_price(text)
            elif "for sale" in text or "to rent" in text:
                strong = p.find("strong")
                if strong:
                    prop["property_type"] = strong.get_text(strip=True)
                span = p.find("span")
                if span:
                    prop["address"] = span.get_text(strip=True)

        # Agent info lives in the next sibling <tr>/<td>
        parent_tr = td.find_parent("tr")
        if parent_tr:
            next_tr = parent_tr.find_next_sibling("tr")
            if next_tr:
                agent_img = next_tr.find("img", src=re.compile(r"agent_logo"))
                if agent_img:
                    prop["agent_logo_url"] = agent_img.get("src")
                phone_link = next_tr.find("a", href=re.compile(r"^tel:"))
                if phone_link:
                    prop["agent_phone"] = phone_link.get_text(strip=True)

        properties.append(prop)

    return properties


def main() -> None:
    eml_path = Path("Price reduced_ 7 properties for sale in London.eml")
    if not eml_path.exists():
        print(f"File not found: {eml_path}", file=sys.stderr)
        sys.exit(1)

    props = parse_zoopla_email(eml_path)
    print(f"Extracted {len(props)} properties:\n")
    for i, p in enumerate(props, 1):
        print(f"--- Property {i} ---")
        for k, v in p.items():
            print(f"  {k}: {v}")
        print()


if __name__ == "__main__":
    main()
