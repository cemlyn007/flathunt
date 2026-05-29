#!/usr/bin/env python3
"""One-shot IMAP recovery: clear ``\\Seen`` on emails whose Dagster runs failed.

The Zoopla and Rightmove email sensors mark alert emails as IMAP-seen *before*
the run executes (see ``src/flathunt/defs/{zoopla,rightmove_email}/alerts.py``).
When a downstream step then fails, the emails stay marked seen and the sensor
never retries them — those listings are silently dropped.

This script reads ``.dagster/history/runs.db`` for FAILED runs in the
``zoopla`` / ``rightmove_email`` job since a cutoff date, pulls the
``Message-Id`` values out of each run's ``run_config.ops.*_property_alerts.
config.message_ids``, then clears the ``\\Seen`` flag on the matching IMAP
messages so the next sensor tick re-batches them.

Notes on the sensor's ``run_key`` dedup:
    Both sensors compute ``run_key = sha256("|".join(sorted(message_ids)))``.
    Dagster dedups RunRequests by ``(sensor_name, run_key)`` permanently. So
    if you unmark a strict subset of one historical batch the resulting
    RunRequest will be deduped and skipped. Unmarking ALL of the failed-run
    message-ids at once produces a brand-new combined hash that won't
    collide; that's the supported pattern here. (If you need finer control,
    delete the failed rows from ``runs.db`` first.)

Usage:
    # Dry-run (default — no IMAP changes, shows what would happen):
    docker compose exec dagster uv run python /app/scripts/unmark_failed_email_runs.py

    # Apply for real:
    docker compose exec dagster uv run python /app/scripts/unmark_failed_email_runs.py --apply

    # Different cutoff date:
    docker compose exec dagster uv run python /app/scripts/unmark_failed_email_runs.py \\
        --since 2026-05-26 --apply

Requires env vars: ``FLATHUNT__IMAP_HOST``, ``FLATHUNT__IMAP_USERNAME``,
``FLATHUNT__IMAP_PASSWORD`` (already set inside the dagster container).
"""

from __future__ import annotations

import argparse
import contextlib
import imaplib
import json
import logging
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger("unmark_failed_email_runs")

_DEFAULT_MAILBOX = "[Gmail]/All Mail"
_DEFAULT_SINCE = "2026-05-26"
_DEFAULT_RUNS_DB = Path("/app/.dagster/history/runs.db")
_PIPELINES = ("zoopla", "rightmove_email")


def _extract_failed_message_ids(runs_db: Path, since: str) -> dict[str, set[str]]:
    """Pull Message-Ids from FAILED runs since ``since``, grouped by pipeline.

    Args:
        runs_db: Path to Dagster's ``runs.db``.
        since: Inclusive ISO date (YYYY-MM-DD); rows with
            ``date(create_timestamp) >= since`` are included.

    Returns:
        Mapping from pipeline name to the set of unique IMAP Message-Id
        strings (with angle brackets, exactly as they appear in
        ``run_config``).
    """
    by_pipeline: dict[str, set[str]] = defaultdict(set)
    placeholders = ",".join("?" * len(_PIPELINES))
    conn = sqlite3.connect(runs_db)
    try:
        cur = conn.execute(
            f"""
            SELECT pipeline_name, run_body
            FROM runs
            WHERE status = 'FAILURE'
              AND pipeline_name IN ({placeholders})
              AND date(create_timestamp) >= ?
            """,
            (*_PIPELINES, since),
        )
        for pipeline, body in cur:
            ops = json.loads(body).get("run_config", {}).get("ops", {})
            for op_val in ops.values():
                msgs = (op_val or {}).get("config", {}).get("message_ids")
                if msgs:
                    by_pipeline[pipeline].update(msgs)
    finally:
        conn.close()
    return dict(by_pipeline)


def _imap_search(conn: imaplib.IMAP4_SSL, message_id: str) -> list[str]:
    """Return server UIDs for messages whose ``Message-Id`` header equals this.

    Args:
        conn: A logged-in, mailbox-selected IMAP connection.
        message_id: The Message-Id to look up, including angle brackets
            (same format Dagster stored in ``run_config``).

    Returns:
        A list of UID strings. Empty if no match. Multiple if the same
        Message-Id appears more than once in the mailbox (Gmail can have
        duplicates across labels via ``[Gmail]/All Mail``).
    """
    status, data = conn.uid("SEARCH", "HEADER", "Message-ID", message_id)
    if status != "OK" or not data or not data[0]:
        return []
    return [uid.decode() for uid in data[0].split()]


def _is_seen(conn: imaplib.IMAP4_SSL, uid: str) -> bool:
    """Return True iff the message currently carries the ``\\Seen`` flag.

    Args:
        conn: A logged-in, mailbox-selected IMAP connection.
        uid: Server UID to inspect.

    Returns:
        True if ``\\Seen`` is set; False otherwise (including on FETCH error
        — caller is expected to have validated the UID first via SEARCH).
    """
    status, data = conn.uid("FETCH", uid, "(FLAGS)")
    if status != "OK" or not data or not data[0]:
        return False
    payload = (
        data[0]
        if isinstance(data[0], bytes)
        else b"".join(p for p in data[0] if isinstance(p, bytes))
    )
    return rb"\Seen" in payload


def _clear_seen(conn: imaplib.IMAP4_SSL, uid: str) -> None:
    """Clear ``\\Seen`` on a single UID (mark it unread).

    Args:
        conn: A logged-in, mailbox-selected IMAP connection.
        uid: Server UID whose flag should be cleared.

    Raises:
        RuntimeError: If the IMAP STORE returns a non-OK status.
    """
    status, _ = conn.uid("STORE", uid, "-FLAGS", r"(\Seen)")
    if status != "OK":
        raise RuntimeError(f"IMAP STORE -FLAGS \\Seen failed for uid={uid}: {status}")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Clear IMAP \\Seen on alert emails whose Dagster runs failed.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--since",
        default=_DEFAULT_SINCE,
        help=f"Inclusive ISO date for FAILED runs (default: {_DEFAULT_SINCE}).",
    )
    p.add_argument(
        "--runs-db",
        type=Path,
        default=_DEFAULT_RUNS_DB,
        help=f"Path to Dagster runs.db (default: {_DEFAULT_RUNS_DB}).",
    )
    p.add_argument(
        "--mailbox",
        default=_DEFAULT_MAILBOX,
        help=f"IMAP mailbox to operate on (default: {_DEFAULT_MAILBOX!r}).",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Actually clear \\Seen. Without this, the script is a dry-run.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code.

    Returns:
        0 on success (everything found and acted on), 1 if some Message-Ids
        could not be found in IMAP, 2 on configuration / connection errors.
    """
    logging.basicConfig(format="%(message)s", level=logging.INFO)
    args = _parse_args(argv)

    host = os.environ.get("FLATHUNT__IMAP_HOST")
    username = os.environ.get("FLATHUNT__IMAP_USERNAME")
    password = os.environ.get("FLATHUNT__IMAP_PASSWORD")
    if not (host and username and password):
        logger.error("FLATHUNT__IMAP_HOST/USERNAME/PASSWORD must all be set in env.")
        return 2

    if not args.runs_db.exists():
        logger.error("runs DB not found at %s", args.runs_db)
        return 2

    by_pipeline = _extract_failed_message_ids(args.runs_db, args.since)
    total = sum(len(s) for s in by_pipeline.values())
    logger.info(
        "Found %d unique Message-Id(s) across %d pipeline(s) "
        "from FAILED runs since %s:",
        total,
        len(by_pipeline),
        args.since,
    )
    for pipeline, msgs in sorted(by_pipeline.items()):
        logger.info("  %s: %d", pipeline, len(msgs))
    if total == 0:
        logger.info("Nothing to do.")
        return 0

    mode = "APPLY (will clear \\Seen)" if args.apply else "DRY-RUN (no changes)"
    logger.info("\nMode:    %s", mode)
    logger.info("Mailbox: %s\n", args.mailbox)

    conn = imaplib.IMAP4_SSL(host)
    try:
        conn.login(username, password)
        # Mirror production code (src/zoopla/imap.py): quote mailbox name
        # because "[Gmail]/All Mail" contains brackets and a space.
        status, _ = conn.select(f'"{args.mailbox}"', readonly=not args.apply)
        if status != "OK":
            logger.error(
                "Could not SELECT mailbox %r (status=%s)", args.mailbox, status
            )
            return 2

        unmarked = already_unseen = not_found = ambiguous = 0
        for pipeline in sorted(by_pipeline):
            logger.info("--- %s ---", pipeline)
            for message_id in sorted(by_pipeline[pipeline]):
                uids = _imap_search(conn, message_id)
                if not uids:
                    logger.info("  ✗ NOT FOUND  %s", message_id)
                    not_found += 1
                    continue
                if len(uids) > 1:
                    logger.info(
                        "  ⚠ AMBIGUOUS (%d matches) uids=%s  %s",
                        len(uids),
                        uids,
                        message_id,
                    )
                    ambiguous += 1
                for uid in uids:
                    if not _is_seen(conn, uid):
                        logger.info("  · already unseen  uid=%s  %s", uid, message_id)
                        already_unseen += 1
                        continue
                    if args.apply:
                        _clear_seen(conn, uid)
                        logger.info("  ✓ unmarked       uid=%s  %s", uid, message_id)
                    else:
                        logger.info("  → would unmark   uid=%s  %s", uid, message_id)
                    unmarked += 1
        verb = "Unmarked" if args.apply else "Would unmark"
        logger.info(
            "\nSummary: %s %d, already-unseen %d, not-found %d, ambiguous %d",
            verb,
            unmarked,
            already_unseen,
            not_found,
            ambiguous,
        )
        if not args.apply and unmarked > 0:
            logger.info("\nRe-run with --apply to make changes.")
        return 0 if not_found == 0 else 1
    finally:
        with contextlib.suppress(Exception):
            conn.close()
        with contextlib.suppress(Exception):
            conn.logout()


if __name__ == "__main__":
    sys.exit(main())
