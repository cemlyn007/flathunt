import email
import email.message
import email.policy
import textwrap
from datetime import UTC, datetime
from pathlib import Path

import pytest

from zoopla.models import AlertType
from zoopla.parser import (
    _extract_listing_id,
    _parse_price,
    parse_zoopla_alert_email,
    parse_zoopla_alert_html,
)

_FIXTURES = Path(__file__).parent / "fixtures"

_CARD_STYLE = (
    "border-left:1px solid #e8e8e8;"
    "border-top:1px solid #e8e8e8;"
    "border-right:1px solid #e8e8e8;"
    "border-radius:8px 8px 0px 0px"
)

_DUMMY_LISTING_CARD = f"""\
<table><tbody><tr>
  <td style="{_CARD_STYLE}">
    <a href="https://www.zoopla.co.uk/for-sale/details/99999999/">
      <img src="https://example.com/img.jpg"/>
    </a>
    <h3>Guide price £300,000</h3>
    <p>Reduced by £10,000</p>
    <p><strong>3 bed terraced house for sale</strong> <span>1 Test Street, London</span></p>
  </td>
</tr></tbody></table>
"""


def _make_minimal_email(subject: str, html_body: str) -> bytes:
    msg = email.message.MIMEPart(policy=email.policy.default)
    msg["Message-ID"] = "<test-id@example.com>"
    msg["Subject"] = subject
    msg["Date"] = "Sat, 25 Apr 2026 12:00:00 +0000"
    msg["MIME-Version"] = "1.0"
    msg["Content-Type"] = "text/html; charset=utf-8"
    msg.set_content(html_body, subtype="html")
    return msg.as_bytes()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def price_reduced_eml_bytes() -> bytes:
    return (_FIXTURES / "price_reduced_7_properties.eml").read_bytes()


@pytest.fixture(scope="module")
def parsed_alert(price_reduced_eml_bytes: bytes):  # type: ignore[return]
    return parse_zoopla_alert_email(price_reduced_eml_bytes)


# ---------------------------------------------------------------------------
# Group 1 — Full email parsing
# ---------------------------------------------------------------------------


def test_parse_alert_email_returns_seven_properties(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the real "Price reduced: 7 properties for sale in London" .eml fixture
    # When   parse_zoopla_alert_email is called (via the module-scoped fixture)
    # Then   the result contains exactly 7 ZooplaProperty items
    assert len(parsed_alert.properties) == 7


def test_parse_alert_email_metadata(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the real fixture
    # When   parse_zoopla_alert_email is called
    # Then   message_id, subject, received_at, and alert_type match expected values
    assert parsed_alert.message_id == "<jdbcOcd3TrWzh2FPBXLgpg@geopod-ismtpd-11>"
    assert parsed_alert.subject == "Price reduced: 7 properties for sale in London"
    assert parsed_alert.received_at == datetime(2026, 4, 25, 17, 18, 48, tzinfo=UTC)
    assert parsed_alert.alert_type == AlertType.PRICE_REDUCED


def test_parse_alert_email_received_at_is_utc(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the real fixture
    # When   parse_zoopla_alert_email is called
    # Then   received_at is timezone-aware and normalised to UTC
    assert parsed_alert.received_at.tzinfo == UTC


# ---------------------------------------------------------------------------
# Group 2 — Per-property field integrity
# ---------------------------------------------------------------------------


def test_first_property_listing_id_is_numeric_string(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert from the real fixture
    # When   the first property is inspected
    # Then   listing_id is a non-empty string of digits
    prop = parsed_alert.properties[0]
    assert prop.listing_id
    assert prop.listing_id.isdigit()


def test_first_property_url_has_no_query_string(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   the first property url is inspected
    # Then   the url contains no query string and points to the correct domain path
    prop = parsed_alert.properties[0]
    assert "?" not in prop.url
    assert prop.url.startswith("https://www.zoopla.co.uk/for-sale/details/")


def test_all_properties_have_price_gbp(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert (price-reduced email — all listings show a price)
    # When   each property is inspected
    # Then   price_gbp is not None for every property
    for prop in parsed_alert.properties:
        assert prop.price_gbp is not None, (
            f"price_gbp is None for listing {prop.listing_id}"
        )


def test_all_properties_have_reduction_gbp(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert (price-reduced email — every card has "Reduced by £X")
    # When   each property is inspected
    # Then   reduction_gbp and reduction_text are both populated
    for prop in parsed_alert.properties:
        assert prop.reduction_gbp is not None, (
            f"reduction_gbp is None for {prop.listing_id}"
        )
        assert prop.reduction_text is not None
        assert "Reduced by" in prop.reduction_text


def test_all_properties_have_address(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   each property is inspected
    # Then   address is not None for every property
    for prop in parsed_alert.properties:
        assert prop.address is not None, (
            f"address is None for listing {prop.listing_id}"
        )


def test_all_properties_have_unique_listing_ids(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   listing_ids are collected
    # Then   all 7 listing_ids are distinct
    ids = [prop.listing_id for prop in parsed_alert.properties]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Group 3 — AlertType classification
# ---------------------------------------------------------------------------


def test_alert_type_price_reduced_when_subject_contains_price_reduced() -> None:
    # Given  a minimal valid email where Subject contains "Price reduced"
    # When   parse_zoopla_alert_email is called
    # Then   alert_type is PRICE_REDUCED
    raw = _make_minimal_email(
        subject="Price reduced: 3 properties for sale in London",
        html_body=_DUMMY_LISTING_CARD,
    )
    alert = parse_zoopla_alert_email(raw)
    assert alert.alert_type == AlertType.PRICE_REDUCED


def test_alert_type_new_listing_when_subject_does_not_contain_price_reduced() -> None:
    # Given  a minimal valid email where Subject does not contain "Price reduced"
    # When   parse_zoopla_alert_email is called
    # Then   alert_type is NEW_LISTING
    raw = _make_minimal_email(
        subject="New listings: 3 properties for sale in London",
        html_body=_DUMMY_LISTING_CARD,
    )
    alert = parse_zoopla_alert_email(raw)
    assert alert.alert_type == AlertType.NEW_LISTING


# ---------------------------------------------------------------------------
# Group 4 — Missing header errors
# ---------------------------------------------------------------------------


def _strip_header(raw: bytes, header: str) -> bytes:
    lines = raw.splitlines(keepends=True)
    return b"".join(
        line for line in lines if not line.lower().startswith(header.lower().encode())
    )


def test_parse_alert_email_raises_on_missing_message_id() -> None:
    # Given  email bytes with no Message-ID header
    # When   parse_zoopla_alert_email is called
    # Then   ValueError is raised
    raw = _strip_header(
        _make_minimal_email("Price reduced: test", _DUMMY_LISTING_CARD),
        "message-id:",
    )
    with pytest.raises(ValueError, match="Message-ID"):
        parse_zoopla_alert_email(raw)


def test_parse_alert_email_raises_on_missing_subject() -> None:
    # Given  email bytes with no Subject header
    # When   parse_zoopla_alert_email is called
    # Then   ValueError is raised
    raw = _strip_header(
        _make_minimal_email("Price reduced: test", _DUMMY_LISTING_CARD),
        "subject:",
    )
    with pytest.raises(ValueError, match="Subject"):
        parse_zoopla_alert_email(raw)


def test_parse_alert_email_raises_on_missing_date() -> None:
    # Given  email bytes with no Date header
    # When   parse_zoopla_alert_email is called
    # Then   ValueError is raised
    raw = _strip_header(
        _make_minimal_email("Price reduced: test", _DUMMY_LISTING_CARD),
        "date:",
    )
    with pytest.raises(ValueError, match="Date"):
        parse_zoopla_alert_email(raw)


def test_parse_alert_email_raises_when_no_html_part() -> None:
    # Given  email bytes with only a text/plain part and no text/html part
    # When   parse_zoopla_alert_email is called
    # Then   ValueError is raised
    plain_only = textwrap.dedent("""\
        Message-ID: <plain-only@example.com>
        Subject: Price reduced: test
        Date: Sat, 25 Apr 2026 12:00:00 +0000
        MIME-Version: 1.0
        Content-Type: text/plain; charset=utf-8

        Just plain text, no HTML.
    """).encode()
    with pytest.raises(ValueError, match="HTML"):
        parse_zoopla_alert_email(plain_only)


# ---------------------------------------------------------------------------
# Group 5 — HTML parser edge cases
# ---------------------------------------------------------------------------


def test_parse_html_empty_string_returns_empty_list() -> None:
    # Given  an empty HTML string
    # When   parse_zoopla_alert_html is called
    # Then   an empty list is returned
    assert parse_zoopla_alert_html("") == []


def test_parse_html_no_matching_cards_returns_empty_list() -> None:
    # Given  HTML with no <td> elements matching the card border-radius style
    # When   parse_zoopla_alert_html is called
    # Then   an empty list is returned
    html = "<html><body><td style='color:red'>no match</td></body></html>"
    assert parse_zoopla_alert_html(html) == []


# ---------------------------------------------------------------------------
# Group 6 — _parse_price (parametrized)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Guide price £375,000", 375000),
        ("Reduced by £25,000", 25000),
        ("£1,200,000", 1200000),
        ("No price here", None),
        ("", None),
    ],
)
def test_parse_price(text: str, expected: int | None) -> None:
    # Given  a price text string
    # When   _parse_price is called
    # Then   the correct integer GBP amount is returned, or None if no £ amount present
    assert _parse_price(text) == expected


# ---------------------------------------------------------------------------
# Group 7 — _extract_listing_id (parametrized)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.zoopla.co.uk/for-sale/details/12345678/", "12345678"),
        (
            "https://www.zoopla.co.uk/for-sale/details/12345678/?utm_source=foo",
            "12345678",
        ),
        ("https://www.zoopla.co.uk/for-sale/flats/london/", None),
        ("", None),
    ],
)
def test_extract_listing_id(url: str, expected: str | None) -> None:
    # Given  a URL string
    # When   _extract_listing_id is called
    # Then   the numeric listing id string is returned, or None if no /details/<id>/ segment
    assert _extract_listing_id(url) == expected


# ---------------------------------------------------------------------------
# Fixtures — new-listings email
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def new_listings_eml_bytes() -> bytes:
    return (_FIXTURES / "new_listings_24_properties.eml").read_bytes()


@pytest.fixture(scope="module")
def parsed_new_listings_alert(new_listings_eml_bytes: bytes):  # type: ignore[return]
    return parse_zoopla_alert_email(new_listings_eml_bytes)


# ---------------------------------------------------------------------------
# Group 8 — New-listings email (includes new-homes properties)
# ---------------------------------------------------------------------------


def test_new_listings_returns_ten_properties(parsed_new_listings_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the real "New listings: 24 new properties for sale in London" .eml fixture
    # When   parse_zoopla_alert_email is called (via the module-scoped fixture)
    # Then   the result contains exactly 10 ZooplaProperty items (visible in email body)
    assert len(parsed_new_listings_alert.properties) == 10


def test_new_listings_alert_type_is_new_listing(parsed_new_listings_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed new-listings alert
    # When   alert_type is inspected
    # Then   it is NEW_LISTING (subject does not contain "Price reduced")
    assert parsed_new_listings_alert.alert_type == AlertType.NEW_LISTING


def test_new_listings_received_at_is_utc(parsed_new_listings_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed new-listings alert
    # When   received_at is inspected
    # Then   it is timezone-aware and normalised to UTC
    assert parsed_new_listings_alert.received_at.tzinfo == UTC


def test_new_listings_received_at_matches_date_header(
    parsed_new_listings_alert,
) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed new-listings alert
    # When   received_at is inspected
    # Then   it matches the Date header value from the fixture (2026-04-25T17:18:48Z)
    assert parsed_new_listings_alert.received_at == datetime(
        2026, 4, 25, 17, 18, 48, tzinfo=UTC
    )


def test_new_listings_all_properties_have_listing_id(parsed_new_listings_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed new-listings alert
    # When   each property is inspected
    # Then   listing_id is a non-empty string of digits
    for prop in parsed_new_listings_alert.properties:
        assert prop.listing_id, "listing_id is empty for a property"
        assert prop.listing_id.isdigit(), (
            f"listing_id is not numeric: {prop.listing_id}"
        )


def test_new_listings_all_properties_have_price_gbp(parsed_new_listings_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed new-listings alert
    # When   each property is inspected
    # Then   price_gbp is not None for every property
    for prop in parsed_new_listings_alert.properties:
        assert prop.price_gbp is not None, (
            f"price_gbp is None for listing {prop.listing_id}"
        )


def test_new_listings_all_properties_have_address(parsed_new_listings_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed new-listings alert
    # When   each property is inspected
    # Then   address is not None for every property
    for prop in parsed_new_listings_alert.properties:
        assert prop.address is not None, (
            f"address is None for listing {prop.listing_id}"
        )


def test_new_listings_all_listing_ids_are_unique(parsed_new_listings_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed new-listings alert
    # When   listing_ids are collected
    # Then   all 10 listing_ids are distinct
    ids = [prop.listing_id for prop in parsed_new_listings_alert.properties]
    assert len(ids) == len(set(ids))


def test_new_listings_contains_new_homes_url(parsed_new_listings_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed new-listings alert (email contains 2 new-homes listings)
    # When   property URLs are inspected
    # Then   at least one URL starts with the new-homes path prefix
    new_homes_urls = [
        prop.url
        for prop in parsed_new_listings_alert.properties
        if prop.url.startswith("https://www.zoopla.co.uk/new-homes/details/")
    ]
    assert len(new_homes_urls) >= 1, "Expected at least one new-homes/details/ URL"


def test_new_listings_no_property_has_reduction_gbp(parsed_new_listings_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed new-listings alert (new listings do not have price reductions)
    # When   each property is inspected
    # Then   reduction_gbp is None for every property
    for prop in parsed_new_listings_alert.properties:
        assert prop.reduction_gbp is None, (
            f"reduction_gbp unexpectedly set for listing {prop.listing_id}"
        )
