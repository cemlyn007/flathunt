import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import dagster as dg
import pytest

from flathunt.defs.resources import ImapResource
from flathunt.defs.rightmove_email.alerts import rightmove_email_sensor
from rightmove.imap import RightmoveRawEmail

_FIXTURES = Path(__file__).parent.parent / "rightmove" / "fixtures"


@pytest.fixture
def fake_imap() -> ImapResource:
    return ImapResource(
        host="imap.example.com",
        port=993,
        username="user",
        password="pass",
    )


@pytest.fixture
def raw_email() -> RightmoveRawEmail:
    return RightmoveRawEmail(
        uid="42",
        message_id="<abc123@mail.rightmove.co.uk>",
        subject="Cemlyn, we've found you 15 properties in London",
        received_at=datetime(2024, 1, 1, tzinfo=UTC),
        raw_bytes=(
            _FIXTURES / "Cemlyn, we've found you 15 properties in London.eml"
        ).read_bytes(),
    )


@pytest.fixture
def mock_checker() -> Callable[[list[RightmoveRawEmail]], MagicMock]:
    def _make_checker(emails: list[RightmoveRawEmail]) -> MagicMock:
        checker = MagicMock()
        checker.__enter__ = MagicMock(return_value=checker)
        checker.__exit__ = MagicMock(return_value=False)
        checker.fetch_unseen_alerts.return_value = emails
        return checker

    return _make_checker


@pytest.fixture(autouse=True)
def stub_run_config(monkeypatch: pytest.MonkeyPatch) -> dict:
    config: dict = {
        "ops": {
            "rightmove_email_matched_properties": {
                "config": {
                    "min_budget": 400000,
                    "max_budget": 775000,
                    "has_floorplans": True,
                    "has_images": True,
                    "min_square_meters": 75.0,
                }
            }
        }
    }
    monkeypatch.setattr(
        "flathunt.defs.rightmove_email.alerts.load_job_run_config",
        lambda _filename: json.loads(json.dumps(config)),
    )
    return config


class TestRightmoveEmailSensor:
    def test_no_emails_yields_no_run_requests(
        self,
        fake_imap: ImapResource,
        mock_checker: Callable[[list[RightmoveRawEmail]], MagicMock],
    ) -> None:
        checker = mock_checker([])
        with patch(
            "flathunt.defs.rightmove_email.alerts.RightmoveImapChecker",
            return_value=checker,
        ):
            ctx = dg.build_sensor_context(resources={"imap": fake_imap})
            result = rightmove_email_sensor(ctx, imap=fake_imap)

        assert isinstance(result, dg.SensorResult)
        assert result.run_requests == []

    def test_run_request_merges_yaml_ops_overrides(
        self,
        fake_imap: ImapResource,
        raw_email: RightmoveRawEmail,
        mock_checker: Callable[[list[RightmoveRawEmail]], MagicMock],
    ) -> None:
        # Given: a YAML preset with rightmove_email_matched_properties filters
        # When: the sensor emits a run request
        # Then: the run_config carries both the YAML ops block and the
        #       per-batch message_ids — i.e. the YAML preset is not dropped
        checker = mock_checker([raw_email])
        with patch(
            "flathunt.defs.rightmove_email.alerts.RightmoveImapChecker",
            return_value=checker,
        ):
            ctx = dg.build_sensor_context(resources={"imap": fake_imap})
            result = rightmove_email_sensor(ctx, imap=fake_imap)

        assert isinstance(result, dg.SensorResult)
        assert result.run_requests is not None
        assert len(result.run_requests) == 1
        run_config = result.run_requests[0].run_config
        matched_cfg = run_config["ops"]["rightmove_email_matched_properties"]["config"]
        assert matched_cfg["min_budget"] == 400000
        assert matched_cfg["max_budget"] == 775000
        assert matched_cfg["has_floorplans"] is True
        assert run_config["ops"]["rightmove_property_alerts"]["config"][
            "message_ids"
        ] == [raw_email.message_id]

    def test_emails_are_marked_seen_in_imap(
        self,
        fake_imap: ImapResource,
        raw_email: RightmoveRawEmail,
        mock_checker: Callable[[list[RightmoveRawEmail]], MagicMock],
    ) -> None:
        checker = mock_checker([raw_email])
        with patch(
            "flathunt.defs.rightmove_email.alerts.RightmoveImapChecker",
            return_value=checker,
        ):
            ctx = dg.build_sensor_context(resources={"imap": fake_imap})
            rightmove_email_sensor(ctx, imap=fake_imap)

        checker.mark_seen.assert_called_once_with([raw_email.uid])
