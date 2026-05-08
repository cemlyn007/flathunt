import email.message
import email.policy
import textwrap
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rightmove.email_parser import (
    _extract_listing_id,
    _parse_price,
    parse_rightmove_alert_email,
    parse_rightmove_alert_html,
)

_FIXTURES = Path(__file__).parent / "fixtures"

_DUMMY_PROPERTY_CARD = """\
<table><tbody><tr>
  <td class="sm-px-0 sm-w-full sm-inline-block" style="width: 50%;" valign="top">
    <table>
      <tr><td bgcolor="#000433"><table><tr><td>5</td></tr></table></td></tr>
      <tr><td class="column">
        <a href="https://www.rightmove.co.uk/properties/99999999?utm_content=v2-ealertspropertyimage">
          <img alt="image" src="https://media.rightmove.co.uk/dir/crop/10:9-16:9/test_max_296x197.jpeg"/>
        </a>
      </td></tr>
      <tr><td style="font-size: 20px; font-weight: 700; color: #000000;">
        <div><div>£300,000</div><div>Guide Price</div></div>
      </td></tr>
      <tr><td><a href="https://www.rightmove.co.uk/properties/99999999?utm_content=v2" style="color: #11828D;">3 bedroom terraced house for sale</a></td></tr>
      <tr><td style="color: #000000; padding-bottom: 12px; font-size: 14px;">Test Street, London, E1</td></tr>
      <tr><td style="font-size: 12px; color: #107A84;">Marketed by Test Agent, London</td></tr>
      <tr><td style="border-top-style: dashed; border-top-color: #888a9a;">
        <a href="tel:020 1234 5678">Call: 020 1234 5678</a>
      </td></tr>
    </table>
  </td>
</tr></tbody></table>
"""


def _make_minimal_email(subject: str, html_body: str) -> bytes:
    msg = email.message.MIMEPart(policy=email.policy.default)
    msg["Message-ID"] = "<test-rightmove@example.com>"
    msg["Subject"] = subject
    msg["Date"] = "Sun, 26 Apr 2026 13:04:00 +0000"
    msg["MIME-Version"] = "1.0"
    msg["Content-Type"] = "text/html; charset=utf-8"
    msg.set_content(html_body, subtype="html")
    return msg.as_bytes()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rightmove_eml_bytes() -> bytes:
    return (
        _FIXTURES / "Cemlyn, we've found you 15 properties in London.eml"
    ).read_bytes()


@pytest.fixture(scope="module")
def parsed_alert(rightmove_eml_bytes: bytes):  # type: ignore[return]
    return parse_rightmove_alert_email(rightmove_eml_bytes)


# ---------------------------------------------------------------------------
# Group 1 — Full email parsing
# ---------------------------------------------------------------------------


def test_parse_alert_email_returns_fourteen_properties(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the real "Cemlyn, we've found you 15 properties in London" .eml fixture
    # When   parse_rightmove_alert_email is called
    # Then   14 properties are parsed (16 card-shaped <td>s exist, 2 have no property URL)
    assert len(parsed_alert.properties) == 14


def test_parse_alert_email_metadata(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the real fixture
    # When   parse_rightmove_alert_email is called
    # Then   message_id, subject, and received_at match expected values
    assert (
        parsed_alert.message_id
        == "<1F.E6.47082.04D0EE96@i-0a29a808e1f9ef1ef.mta3vrest.sd.prd.sparkpost>"
    )
    assert parsed_alert.subject == "Cemlyn, we've found you 15 properties in London"
    assert parsed_alert.received_at == datetime(2026, 4, 26, 13, 4, 0, tzinfo=UTC)


def test_parse_alert_email_received_at_is_utc(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the real fixture
    # When   parse_rightmove_alert_email is called
    # Then   received_at is timezone-aware and normalised to UTC
    assert parsed_alert.received_at.tzinfo == UTC


# ---------------------------------------------------------------------------
# Group 2 — Per-property field integrity
# ---------------------------------------------------------------------------


def test_first_property_listing_id(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert from the real fixture
    # When   the first property is inspected
    # Then   listing_id is the expected numeric string
    assert parsed_alert.properties[0].listing_id == "174935852"


def test_first_property_url_has_no_query_string(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   the first property url is inspected
    # Then   the url is clean (no query string) and points to the correct listing
    prop = parsed_alert.properties[0]
    assert prop.url == "https://www.rightmove.co.uk/properties/174935852"
    assert "?" not in prop.url


def test_first_property_price(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   the first property price is inspected
    # Then   price_gbp and price_qualifier match expected values
    prop = parsed_alert.properties[0]
    assert prop.price_gbp == 425000
    assert prop.price_qualifier == "Offers in Region of"


def test_first_property_is_not_reduced(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   the first property is inspected
    # Then   is_reduced is False (no Reduced badge in top bar)
    assert parsed_alert.properties[0].is_reduced is False


def test_all_properties_have_listing_id(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   each property is inspected
    # Then   listing_id is a non-empty numeric string
    for prop in parsed_alert.properties:
        assert prop.listing_id
        assert prop.listing_id.isdigit(), (
            f"listing_id is not numeric: {prop.listing_id}"
        )


def test_all_properties_have_price_gbp(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   each property is inspected
    # Then   price_gbp is not None for every property
    for prop in parsed_alert.properties:
        assert prop.price_gbp is not None, f"price_gbp is None for {prop.listing_id}"


def test_all_properties_have_address(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   each property is inspected
    # Then   address is not None for every property
    for prop in parsed_alert.properties:
        assert prop.address is not None, f"address is None for {prop.listing_id}"


def test_all_properties_have_agent_phone(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   each property is inspected
    # Then   agent_phone is not None for every property
    for prop in parsed_alert.properties:
        assert prop.agent_phone is not None, (
            f"agent_phone is None for {prop.listing_id}"
        )


def test_all_properties_have_image_url(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   each property is inspected
    # Then   image_url is not None and points to the Rightmove media CDN
    for prop in parsed_alert.properties:
        assert prop.image_url is not None, f"image_url is None for {prop.listing_id}"
        assert prop.image_url.startswith("https://media.rightmove.co.uk/"), (
            f"unexpected image domain for {prop.listing_id}: {prop.image_url}"
        )


def test_all_properties_have_unique_listing_ids(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   listing_ids are collected
    # Then   all 14 listing_ids are distinct
    ids = [prop.listing_id for prop in parsed_alert.properties]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Group 3 — Reduced badge
# ---------------------------------------------------------------------------


def test_reduced_properties_count(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   reduced properties are counted
    # Then   exactly 6 properties have the Reduced badge
    reduced = [p for p in parsed_alert.properties if p.is_reduced]
    assert len(reduced) == 6


def test_third_property_is_reduced(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   the third property (index 2, listing 87618546) is inspected
    # Then   is_reduced is True
    prop = parsed_alert.properties[2]
    assert prop.listing_id == "87618546"
    assert prop.is_reduced is True


# ---------------------------------------------------------------------------
# Group 4 — Price qualifier variations
# ---------------------------------------------------------------------------


def test_qualifier_offers_in_region_of(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    assert parsed_alert.properties[0].price_qualifier == "Offers in Region of"


def test_qualifier_offers_over(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    prop = parsed_alert.properties[4]
    assert prop.listing_id == "174935555"
    assert prop.price_qualifier == "Offers Over"


def test_qualifier_guide_price(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    prop = parsed_alert.properties[6]
    assert prop.listing_id == "174935996"
    assert prop.price_qualifier == "Guide Price"


def test_qualifier_shared_ownership(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    prop = parsed_alert.properties[8]
    assert prop.listing_id == "174936440"
    assert prop.price_qualifier == "Shared ownership"


def test_all_properties_have_photo_and_floorplan_count(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   each property is inspected
    # Then   photo_count and floorplan_count are both non-None positive integers
    for prop in parsed_alert.properties:
        assert prop.photo_count is not None and prop.photo_count > 0, (
            f"photo_count missing for {prop.listing_id}"
        )
        assert prop.floorplan_count is not None and prop.floorplan_count > 0, (
            f"floorplan_count missing for {prop.listing_id}"
        )


def test_first_property_photo_and_floorplan_count(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   the first property is inspected
    # Then   photo_count and floorplan_count match expected values from the fixture
    prop = parsed_alert.properties[0]
    assert prop.photo_count == 20
    assert prop.floorplan_count == 1


def test_qualifier_none_when_absent(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  a property with no price qualifier (index 1, listing 174935918)
    # When   price_qualifier is inspected
    # Then   it is None
    prop = parsed_alert.properties[1]
    assert prop.listing_id == "174935918"
    assert prop.price_qualifier is None


# ---------------------------------------------------------------------------
# Group 5 — Missing header errors
# ---------------------------------------------------------------------------


def _strip_header(raw: bytes, header: str) -> bytes:
    lines = raw.splitlines(keepends=True)
    return b"".join(
        line for line in lines if not line.lower().startswith(header.lower().encode())
    )


def test_parse_alert_email_raises_on_missing_message_id() -> None:
    # Given  email bytes with no Message-ID header
    # When   parse_rightmove_alert_email is called
    # Then   ValueError is raised
    raw = _strip_header(
        _make_minimal_email("15 properties in London", _DUMMY_PROPERTY_CARD),
        "message-id:",
    )
    with pytest.raises(ValueError, match="Message-ID"):
        parse_rightmove_alert_email(raw)


def test_parse_alert_email_raises_on_missing_subject() -> None:
    # Given  email bytes with no Subject header
    # When   parse_rightmove_alert_email is called
    # Then   ValueError is raised
    raw = _strip_header(
        _make_minimal_email("15 properties in London", _DUMMY_PROPERTY_CARD),
        "subject:",
    )
    with pytest.raises(ValueError, match="Subject"):
        parse_rightmove_alert_email(raw)


def test_parse_alert_email_raises_on_missing_date() -> None:
    # Given  email bytes with no Date header
    # When   parse_rightmove_alert_email is called
    # Then   ValueError is raised
    raw = _strip_header(
        _make_minimal_email("15 properties in London", _DUMMY_PROPERTY_CARD),
        "date:",
    )
    with pytest.raises(ValueError, match="Date"):
        parse_rightmove_alert_email(raw)


def test_parse_alert_email_raises_when_no_html_part() -> None:
    # Given  email bytes with only a text/plain part
    # When   parse_rightmove_alert_email is called
    # Then   ValueError is raised
    plain_only = textwrap.dedent("""\
        Message-ID: <plain-only@example.com>
        Subject: 15 properties in London
        Date: Sun, 26 Apr 2026 13:04:00 +0000
        MIME-Version: 1.0
        Content-Type: text/plain; charset=utf-8

        Just plain text, no HTML.
    """).encode()
    with pytest.raises(ValueError, match="HTML"):
        parse_rightmove_alert_email(plain_only)


# ---------------------------------------------------------------------------
# Group 6 — HTML parser edge cases
# ---------------------------------------------------------------------------


def test_parse_html_empty_string_returns_empty_list() -> None:
    # Given  an empty HTML string
    # When   parse_rightmove_alert_html is called
    # Then   an empty list is returned
    assert parse_rightmove_alert_html("") == []


def test_parse_html_no_matching_cards_returns_empty_list() -> None:
    # Given  HTML with no <td> elements matching the card classes
    # When   parse_rightmove_alert_html is called
    # Then   an empty list is returned
    html = "<html><body><td style='color:red'>no match</td></body></html>"
    assert parse_rightmove_alert_html(html) == []


# ---------------------------------------------------------------------------
# Group 7 — _parse_price (parametrized)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("£425,000", 425000),
        ("£2,400,000", 2400000),
        ("£106,750", 106750),
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
# Group 8 — _extract_listing_id (parametrized)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.rightmove.co.uk/properties/174935852", "174935852"),
        (
            "https://www.rightmove.co.uk/properties/174935852?utm_content=foo",
            "174935852",
        ),
        ("https://www.rightmove.co.uk/other/path", None),
        ("", None),
    ],
)
def test_extract_listing_id(url: str, expected: str | None) -> None:
    # Given  a URL string
    # When   _extract_listing_id is called
    # Then   the numeric listing id string is returned, or None if absent
    assert _extract_listing_id(url) == expected
