#!/usr/bin/env python3
"""Boot-time reconciler: fail Dagster runs orphaned by a container restart.

This deployment runs a single-container ``dagster dev`` with the
``DefaultRunLauncher`` (run workers are subprocesses of the gRPC code server).
When the container restarts, any in-flight worker dies but its run stays marked
``STARTED``/``STARTING`` in ``runs.db`` forever — ``DefaultRunLauncher`` reports
``supports_check_run_worker_health = False``, so ``run_monitoring`` never
reconciles it. Those zombie runs clutter the UI and slowly eat the
``QueuedRunCoordinator`` concurrency budget.

This script is meant to run **once, at container boot, before ``dagster dev``
starts** (see ``docker-compose.yml``). At that instant no daemon, webserver, or
grpc server is up yet, so any ``STARTED``/``STARTING`` run is provably a zombie
from the previous life of the container and is safe to fail. ``QUEUED`` runs are
deliberately left untouched: they have no worker yet and the coordinator will
dequeue them normally once ``dagster dev`` comes up.

The script never blocks boot: operational errors are logged and it still exits
0, so ``python fail_orphaned_runs.py && dagster dev`` can't be wedged by a
transient cleanup hiccup.

Usage:
    # Real run (default) — fails leftover STARTED/STARTING runs:
    docker compose exec dagster python /app/scripts/fail_orphaned_runs.py

    # Inspect only, change nothing:
    docker compose exec dagster python /app/scripts/fail_orphaned_runs.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys

from dagster import DagsterInstance
from dagster._core.storage.dagster_run import DagsterRunStatus, RunsFilter

logger = logging.getLogger("fail_orphaned_runs")

_ORPHAN_MESSAGE = (
    "Failed by boot reconciler (scripts/fail_orphaned_runs.py): run worker did "
    "not survive a container restart. DefaultRunLauncher does not support run "
    "worker health checks, so this STARTED/STARTING run was orphaned."
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Fail Dagster runs orphaned by a container restart.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="List orphaned runs without failing them.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Always returns 0 so it can never block container boot.

    Returns:
        0 unconditionally. A non-zero exit would wedge the ``&& dagster dev``
        boot chain over a transient reconcile error, which is never worth it.
    """
    logging.basicConfig(format="%(message)s", level=logging.INFO)
    args = _parse_args(argv)

    try:
        orphan_statuses = [DagsterRunStatus.STARTED, DagsterRunStatus.STARTING]
        instance = DagsterInstance.get()
        runs = instance.get_runs(
            filters=RunsFilter(statuses=orphan_statuses), limit=1000
        )
        if not runs:
            logger.info("No orphaned STARTED/STARTING runs to reconcile.")
            return 0

        verb = "Would fail" if args.dry_run else "Failing"
        logger.info("%s %d orphaned run(s):", verb, len(runs))
        for run in runs:
            logger.info("  %s  %s  job=%s", run.status.value, run.run_id, run.job_name)
            if not args.dry_run:
                instance.report_run_failed(run, _ORPHAN_MESSAGE)
        if args.dry_run:
            logger.info("Dry run: nothing changed.")
        else:
            logger.info("Reconciled %d orphaned run(s).", len(runs))
    except Exception:  # Boot must proceed regardless of reconcile errors.
        logger.exception("Orphan reconcile failed; leaving runs as-is and continuing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
