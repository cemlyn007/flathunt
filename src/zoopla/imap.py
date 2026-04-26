import email
import email.utils
import imaplib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

__all__ = ["ZooplaImapChecker", "ZooplaRawEmail"]


@dataclass
class ZooplaRawEmail:
    uid: str
    message_id: str
    subject: str
    received_at: datetime
    raw_bytes: bytes


class ZooplaImapChecker:
    def __init__(
        self, host: str, port: int, username: str, password: str, mailbox: str = "INBOX"
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._mailbox = mailbox
        self._connection: imaplib.IMAP4_SSL | None = None

    def __enter__(self) -> "ZooplaImapChecker":
        self._connection = imaplib.IMAP4_SSL(self._host, self._port)
        self._connection.login(self._username, self._password)
        self._connection.select(self._mailbox, readonly=False)
        return self

    def __exit__(self, *args: object) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
                self._connection.logout()
            except Exception:
                logger.exception("Error closing IMAP connection")
            finally:
                self._connection = None

    def _require_connection(self) -> imaplib.IMAP4_SSL:
        if self._connection is None:
            raise RuntimeError("Not connected; use as a context manager")
        return self._connection

    def fetch_unseen_alerts(self) -> list[ZooplaRawEmail]:
        conn = self._require_connection()
        status, data = conn.uid("SEARCH", "UNSEEN", 'FROM "propertyalerts"')
        if status != "OK":
            raise RuntimeError(f"IMAP SEARCH failed: {status}")

        raw_uids: list[bytes] = data[0].split() if data[0] else []
        if not raw_uids:
            return []

        uid_list = ",".join(uid.decode() for uid in raw_uids)
        status, fetch_data = conn.uid("FETCH", uid_list, "(RFC822)")
        if status != "OK":
            raise RuntimeError(f"IMAP FETCH failed: {status}")

        results: list[ZooplaRawEmail] = []
        for i in range(0, len(fetch_data), 2):
            response_part = fetch_data[i]
            if not isinstance(response_part, tuple):
                continue
            header_line, raw_bytes = response_part
            uid_str = _extract_uid(header_line)
            msg = email.message_from_bytes(raw_bytes)
            subject = msg.get("Subject", "")
            message_id = msg.get("Message-ID", "")
            date_str = msg.get("Date", "")
            received_at = _parse_date(date_str)
            results.append(
                ZooplaRawEmail(
                    uid=uid_str,
                    message_id=message_id,
                    subject=subject,
                    received_at=received_at,
                    raw_bytes=raw_bytes,
                )
            )

        return results

    def fetch_by_message_id(self, message_id: str) -> ZooplaRawEmail:
        conn = self._require_connection()
        status, data = conn.uid("SEARCH", "HEADER", "Message-ID", message_id)
        if status != "OK":
            raise RuntimeError(f"IMAP SEARCH failed: {status}")
        raw_uids = data[0].split() if data[0] else []
        if not raw_uids:
            raise KeyError(f"No email found with Message-ID {message_id!r}")
        uid_str = raw_uids[0].decode()
        status, fetch_data = conn.uid("FETCH", uid_str, "(RFC822)")
        if status != "OK":
            raise RuntimeError(f"IMAP FETCH failed: {status}")
        response_part = fetch_data[0]
        if not isinstance(response_part, tuple):
            raise RuntimeError(f"Unexpected FETCH response for {message_id!r}")
        _, raw_bytes = response_part
        msg = email.message_from_bytes(raw_bytes)
        subject = msg.get("Subject", "")
        date_str = msg.get("Date", "")
        received_at = _parse_date(date_str)
        return ZooplaRawEmail(
            uid=uid_str,
            message_id=message_id,
            subject=subject,
            received_at=received_at,
            raw_bytes=raw_bytes,
        )

    def mark_seen(self, uids: list[str]) -> None:
        if not uids:
            return
        conn = self._require_connection()
        uid_list = ",".join(uids)
        status, _ = conn.uid("STORE", uid_list, "+FLAGS", r"(\Seen)")
        if status != "OK":
            raise RuntimeError(f"IMAP STORE failed: {status}")


def _extract_uid(header_line: bytes) -> str:
    parts = header_line.split()
    for i, part in enumerate(parts):
        if part.lstrip(b"(").upper() == b"UID" and i + 1 < len(parts):
            return parts[i + 1].rstrip(b")").decode()
    return header_line.decode(errors="replace")


def _parse_date(date_str: str) -> datetime:
    if not date_str:
        return datetime.now(UTC)
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        return dt.astimezone(UTC)
    except Exception:
        logger.warning("Could not parse email date %r, using current time", date_str)
        return datetime.now(UTC)
