from datetime import UTC, datetime
from pathlib import Path

import pytest

from zoopla.models import AlertType
from zoopla.parser import parse_zoopla_alert_email

_FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def new_listings_eml_bytes() -> bytes:
    return (_FIXTURES / "new_listings_24_properties.eml").read_bytes()


@pytest.fixture(scope="module")
def parsed_alert(new_listings_eml_bytes: bytes):  # type: ignore[return]
    return parse_zoopla_alert_email(new_listings_eml_bytes)


# ---------------------------------------------------------------------------
# Group 1 — Alert-level metadata
# ---------------------------------------------------------------------------


def test_alert_type_is_new_listing(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  a "New listings" Zoopla alert email
    # When   parse_zoopla_alert_email is called
    # Then   alert_type is NEW_LISTING (subject does not contain "Price reduced")
    assert parsed_alert.alert_type == AlertType.NEW_LISTING


def test_alert_metadata(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the "New listings: 24 new properties for sale in London" .eml fixture
    # When   parse_zoopla_alert_email is called
    # Then   message_id, subject, and received_at match the email headers
    assert parsed_alert.message_id == "<jdbcOcd3TrWzh2FPBXLgpg@geopod-ismtpd-11>"
    assert parsed_alert.subject == "New listings: 24 new properties for sale in London"
    assert parsed_alert.received_at == datetime(2026, 4, 25, 17, 18, 48, tzinfo=UTC)


def test_received_at_is_utc(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the new listings fixture
    # When   the parsed alert is inspected
    # Then   received_at is timezone-aware and normalised to UTC
    assert parsed_alert.received_at.tzinfo == UTC


# ---------------------------------------------------------------------------
# Group 2 — Property count
# ---------------------------------------------------------------------------


def test_parsed_property_count_is_ten(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  an email whose subject advertises 24 properties
    # When   parse_zoopla_alert_email is called
    # Then   10 properties are returned (the email body shows a selection;
    #        2 additional cards are skipped because they lack a valid listing URL)
    assert len(parsed_alert.properties) == 10


# ---------------------------------------------------------------------------
# Group 3 — Listing-level field integrity
# ---------------------------------------------------------------------------


def test_all_properties_have_numeric_listing_id(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed new listings alert
    # When   each property is inspected
    # Then   listing_id is a non-empty string of digits
    for prop in parsed_alert.properties:
        assert prop.listing_id, f"empty listing_id for {prop}"
        assert prop.listing_id.isdigit(), f"non-numeric listing_id: {prop.listing_id!r}"


def test_all_properties_url_has_no_query_string(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert (a new listings email can include both for-sale and new-homes listings)
    # When   each property URL is inspected
    # Then   URLs contain no tracking parameters and point to a Zoopla details path
    valid_prefixes = (
        "https://www.zoopla.co.uk/for-sale/details/",
        "https://www.zoopla.co.uk/new-homes/details/",
    )
    for prop in parsed_alert.properties:
        assert "?" not in prop.url, f"query string found in url: {prop.url!r}"
        assert prop.url.startswith(valid_prefixes), f"unexpected url path: {prop.url!r}"


def test_all_properties_have_unique_listing_ids(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   listing_ids are collected
    # Then   all 8 listing_ids are distinct
    ids = [prop.listing_id for prop in parsed_alert.properties]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Group 4 — Price fields
# ---------------------------------------------------------------------------


def test_all_properties_have_price_gbp(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed new listings alert (all listings display a guide price)
    # When   each property is inspected
    # Then   price_gbp is a positive integer for every property
    for prop in parsed_alert.properties:
        assert prop.price_gbp is not None, f"price_gbp is None for {prop.listing_id}"
        assert prop.price_gbp > 0


def test_no_properties_have_reduction(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  a new listings alert (not a price-reduced alert)
    # When   each property is inspected
    # Then   reduction_gbp and reduction_text are both None — no reductions exist
    for prop in parsed_alert.properties:
        assert prop.reduction_gbp is None, (
            f"unexpected reduction_gbp={prop.reduction_gbp} for {prop.listing_id}"
        )
        assert prop.reduction_text is None, (
            f"unexpected reduction_text={prop.reduction_text!r} for {prop.listing_id}"
        )


# ---------------------------------------------------------------------------
# Group 5 — Property type and address
# ---------------------------------------------------------------------------


def test_all_properties_have_address(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   each property is inspected
    # Then   address is not None for every property
    for prop in parsed_alert.properties:
        assert prop.address is not None, f"address is None for {prop.listing_id}"


def test_all_properties_have_property_type_containing_for_sale(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   each property_type is inspected
    # Then   it is not None and contains "for sale"
    for prop in parsed_alert.properties:
        assert prop.property_type is not None, (
            f"property_type is None for {prop.listing_id}"
        )
        assert "for sale" in prop.property_type, (
            f"'for sale' not in property_type {prop.property_type!r} for {prop.listing_id}"
        )


# ---------------------------------------------------------------------------
# Group 6 — Agent fields
# ---------------------------------------------------------------------------


def test_all_properties_have_agent_logo(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   each property is inspected
    # Then   agent_logo_url is present (new listing emails include agent branding)
    for prop in parsed_alert.properties:
        assert prop.agent_logo_url is not None, (
            f"agent_logo_url is None for {prop.listing_id}"
        )


def test_no_properties_have_agent_phone(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed new listings alert
    # When   each property is inspected
    # Then   agent_phone is None for every property (no tel: links in this email format)
    for prop in parsed_alert.properties:
        assert prop.agent_phone is None, (
            f"unexpected agent_phone={prop.agent_phone!r} for {prop.listing_id}"
        )


def test_all_properties_have_image(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   each property is inspected
    # Then   image_url is present for every property
    for prop in parsed_alert.properties:
        assert prop.image_url is not None, f"image_url is None for {prop.listing_id}"


# ---------------------------------------------------------------------------
# Group 7 — Spot-check first property
# ---------------------------------------------------------------------------


def test_first_property_spot_check(parsed_alert) -> None:  # type: ignore[no-untyped-def]
    # Given  the parsed alert
    # When   the first property is inspected
    # Then   its known field values match the source email
    prop = parsed_alert.properties[0]
    assert prop.listing_id == "73031106"
    assert prop.price_gbp == 325000
    assert prop.address == "Romford Road, London E15"
    assert prop.property_type == "2 bed flat for sale"
