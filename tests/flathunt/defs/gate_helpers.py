"""Shared test helpers for conditional-materialization 'gate' assets.

A gate asset uses ``output_required=False`` and yields either:
- exactly one ``dg.Output`` (non-empty result), or
- exactly one ``dg.AssetObservation`` (empty result -> downstream Skipped).

``drain_gate`` consumes the generator returned by calling such an asset directly
and returns the Output's value (``[]`` when the gate skipped) plus any
observations, so existing list-based assertions keep working.
"""

from collections.abc import Iterator
from typing import Any

import dagster as dg


def drain_gate(
    gen: Iterator[Any],
) -> tuple[list[Any], list[dg.AssetObservation]]:
    """Drain a gate generator into (value, observations).

    Args:
        gen: The generator returned by calling a gate asset function directly.

    Returns:
        A 2-tuple of the single Output's value (or ``[]`` if the gate yielded no
        Output, i.e. it skipped) and the list of yielded AssetObservation events.
    """
    events = list(gen)
    outputs = [e for e in events if isinstance(e, dg.Output)]
    observations = [e for e in events if isinstance(e, dg.AssetObservation)]
    value = outputs[0].value if outputs else []
    return value, observations
