import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import dagster as dg
import pytest

from flathunt.defs.resources import ImapResource
from flathunt.defs.zoopla_alerts import (
    ZooplaAlertsConfig,
    zoopla_email_sensor,
    zoopla_property_alerts,
)
from zoopla.imap import ZooplaRawEmail
from zoopla.models import AlertType, ZooplaPropertyAlert

_FIXTURES = Path(__file__).parent.parent / "zoopla" / "fixtures"


@pytest.fixture
def fake_imap() -> ImapResource:
    return ImapResource(
        host="imap.example.com",
        port=993,
        username="user",
        password="pass",
    )


@pytest.fixture
def raw_email() -> ZooplaRawEmail:
    return ZooplaRawEmail(
        uid="42",
        message_id="<abc123@mail.zoopla.co.uk>",
        subject="New listings alert",
        received_at=datetime(2024, 1, 1, tzinfo=UTC),
        raw_bytes=(_FIXTURES / "new_listings_24_properties.eml").read_bytes(),
    )


@pytest.fixture
def mock_checker(
    raw_email: ZooplaRawEmail,
) -> Callable[[list[ZooplaRawEmail]], MagicMock]:
    def _make_checker(emails: list[ZooplaRawEmail]) -> MagicMock:
        checker = MagicMock()
        checker.__enter__ = MagicMock(return_value=checker)
        checker.__exit__ = MagicMock(return_value=False)
        checker.fetch_unseen_alerts.return_value = emails
        return checker

    return _make_checker


# ---------------------------------------------------------------------------
# Sensor tests
# ---------------------------------------------------------------------------


class TestZooplaEmailSensor:
    def test_no_emails_yields_no_run_requests(
        self,
        fake_imap: ImapResource,
        mock_checker: Callable[[list[ZooplaRawEmail]], MagicMock],
    ) -> None:
        # Given: no unseen emails are available
        # When: the sensor runs
        # Then: no run requests are generated
        checker = mock_checker([])
        with patch(
            "flathunt.defs.zoopla_alerts.ZooplaImapChecker", return_value=checker
        ):
            ctx = dg.build_sensor_context(resources={"imap": fake_imap})
            result = zoopla_email_sensor(ctx, imap=fake_imap)

        assert isinstance(result, dg.SensorResult)
        assert result.run_requests == []
        assert result.cursor is not None
        cursor = json.loads(result.cursor)
        assert cursor["seen_message_ids"] == []

    def test_new_email_produces_run_request_with_message_id(
        self,
        fake_imap: ImapResource,
        raw_email: ZooplaRawEmail,
        mock_checker: Callable[[list[ZooplaRawEmail]], MagicMock],
    ) -> None:
        # Given: a new unseen email is available
        # When: the sensor runs
        # Then: a run request is created with the email's message ID
        checker = mock_checker([raw_email])
        with patch(
            "flathunt.defs.zoopla_alerts.ZooplaImapChecker", return_value=checker
        ):
            ctx = dg.build_sensor_context(resources={"imap": fake_imap})
            result = zoopla_email_sensor(ctx, imap=fake_imap)

        assert isinstance(result, dg.SensorResult)
        assert result.run_requests is not None
        assert len(result.run_requests) == 1
        req = result.run_requests[0]
        assert req.run_key == raw_email.message_id
        ops_config = req.run_config["ops"]["zoopla_property_alerts"]["config"]
        assert ops_config["message_id"] == raw_email.message_id

    def test_seen_email_is_not_requeued(
        self,
        fake_imap: ImapResource,
        raw_email: ZooplaRawEmail,
        mock_checker: Callable[[list[ZooplaRawEmail]], MagicMock],
    ) -> None:
        # Given: an email that was previously seen (in cursor state)
        # When: the sensor runs and encounters that same email
        # Then: no run request is created for it
        cursor = json.dumps({"seen_message_ids": [raw_email.message_id]})
        checker = mock_checker([raw_email])
        with patch(
            "flathunt.defs.zoopla_alerts.ZooplaImapChecker", return_value=checker
        ):
            ctx = dg.build_sensor_context(cursor=cursor, resources={"imap": fake_imap})
            result = zoopla_email_sensor(ctx, imap=fake_imap)

        assert isinstance(result, dg.SensorResult)
        assert result.run_requests == []

    def test_seen_ids_are_persisted_in_cursor(
        self,
        fake_imap: ImapResource,
        raw_email: ZooplaRawEmail,
        mock_checker: Callable[[list[ZooplaRawEmail]], MagicMock],
    ) -> None:
        # Given: a new unseen email is available
        # When: the sensor processes it
        # Then: the email's message ID is persisted in the cursor state
        checker = mock_checker([raw_email])
        with patch(
            "flathunt.defs.zoopla_alerts.ZooplaImapChecker", return_value=checker
        ):
            ctx = dg.build_sensor_context(resources={"imap": fake_imap})
            result = zoopla_email_sensor(ctx, imap=fake_imap)

        assert isinstance(result, dg.SensorResult)
        assert result.cursor is not None
        cursor = json.loads(result.cursor)
        assert raw_email.message_id in cursor["seen_message_ids"]

    def test_new_emails_are_marked_seen_in_imap(
        self,
        fake_imap: ImapResource,
        raw_email: ZooplaRawEmail,
        mock_checker: Callable[[list[ZooplaRawEmail]], MagicMock],
    ) -> None:
        # Given: a new unseen email is available
        # When: the sensor processes it
        # Then: the email is marked as seen in the IMAP server
        checker = mock_checker([raw_email])
        with patch(
            "flathunt.defs.zoopla_alerts.ZooplaImapChecker", return_value=checker
        ):
            ctx = dg.build_sensor_context(resources={"imap": fake_imap})
            zoopla_email_sensor(ctx, imap=fake_imap)

        checker.mark_seen.assert_called_once_with([raw_email.uid])


# ---------------------------------------------------------------------------
# Asset tests
# ---------------------------------------------------------------------------


class TestZooplaPropertyAlertsAsset:
    def test_empty_message_id_returns_empty_alert(
        self, fake_imap: ImapResource
    ) -> None:
        # Given: an empty message ID in the config
        # When: the asset is executed
        # Then: an alert with no properties is returned
        ctx = dg.build_asset_context()
        config = ZooplaAlertsConfig(message_id="")
        alert = zoopla_property_alerts(ctx, config=config, imap=fake_imap)

        assert isinstance(alert, ZooplaPropertyAlert)
        assert alert.properties == []
        assert alert.message_id == ""

    def test_message_id_fetches_and_parses_email(
        self, fake_imap: ImapResource, raw_email: ZooplaRawEmail
    ) -> None:
        # Given: a valid message ID in the config
        # When: the asset is executed
        # Then: the email is fetched from IMAP and parsed into alert properties
        checker = MagicMock()
        checker.__enter__ = MagicMock(return_value=checker)
        checker.__exit__ = MagicMock(return_value=False)
        checker.fetch_by_message_id.return_value = raw_email

        ctx = dg.build_asset_context()
        config = ZooplaAlertsConfig(message_id=raw_email.message_id)
        with patch(
            "flathunt.defs.zoopla_alerts.ZooplaImapChecker", return_value=checker
        ):
            alert = zoopla_property_alerts(ctx, config=config, imap=fake_imap)

        checker.fetch_by_message_id.assert_called_once_with(raw_email.message_id)
        assert isinstance(alert, ZooplaPropertyAlert)
        assert alert.alert_type == AlertType.NEW_LISTING
        assert len(alert.properties) == 10
