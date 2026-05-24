"""Locks the Dagster behaviour the skip-frontier feature relies on.

Two cheap, robust checks:
1. ``drain_gate`` correctly splits a stream of yielded events into value +
   observations (uses hand-built event iterators — no Dagster execution).
2. An ``output_required=False`` asset that yields no Output skips its downstream
   while the run succeeds (uses a config-free toy gate + ``dg.materialize``).
A Dagster upgrade that changes these semantics fails here, loudly, rather than
silently in the real pipelines.
"""

from collections.abc import Iterator

import dagster as dg

from tests.flathunt.defs.gate_helpers import drain_gate


def test_drain_gate_extracts_output_value() -> None:
    """A single Output is unwrapped to its value; no observations."""
    value, observations = drain_gate(iter([dg.Output([1, 2], metadata={"passed": 2})]))
    assert value == [1, 2]
    assert observations == []


def test_drain_gate_reports_skip_as_empty_with_observation() -> None:
    """A single AssetObservation (no Output) reads as empty value + the observation."""
    obs = dg.AssetObservation(asset_key=dg.AssetKey("x"), metadata={"passed": 0})
    value, observations = drain_gate(iter([obs]))
    assert value == []
    assert len(observations) == 1


@dg.asset(output_required=False)
def _toy_skip_gate(
    context: dg.AssetExecutionContext,
) -> Iterator[dg.Output[list[int]] | dg.AssetObservation]:
    # Always skips: yields an observation, never an Output.
    yield dg.AssetObservation(asset_key=context.asset_key, metadata={"passed": 0})


@dg.asset
def _toy_downstream(_toy_skip_gate: list[int]) -> int:
    return len(_toy_skip_gate)


def test_materialize_skips_downstream_when_gate_yields_no_output() -> None:
    """No Output from the gate -> downstream Skipped, run still succeeds."""
    result = dg.materialize([_toy_skip_gate, _toy_downstream], raise_on_error=False)
    assert result.success is True
    materialized = [
        e.asset_key.to_user_string()
        for e in result.get_asset_materialization_events()
        if e.asset_key is not None
    ]
    assert "_toy_downstream" not in materialized
    assert len(result.get_asset_observation_events()) == 1
