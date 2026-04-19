"""Investigate whether TfL timetable API can replace Journey Planner API calls.

Current approach in transport.py:
  For each line with N stops → N*(N-1)/2 Journey Planner API calls.

Hypothesis:
  GET /Line/{lineId}/Timetable/{fromStopPointId}?direction={dir} returns
  station_intervals with cumulative time_to_arrival for all subsequent stops on
  the route.  Stops appear in pairs (arrival, then departure), which lets us
  derive adjacent-stop and any-pair travel times from N timetable calls instead
  of N*(N-1)/2 journey planner calls.

This script:
  1. Picks a representative line (default: central).
  2. Fetches its stop points.
  3. Calls get_timetable for the first stop (trying inbound then outbound).
  4. Shows the raw interval structure and explains the arrival/departure pairing.
  5. Extracts pairwise travel times correctly.
  6. Cross-checks a sample of pairs against the Journey Planner (--validate).
  7. Prints an API call count comparison.

Usage:
    uv run python scripts/investigate_tfl_timetable.py
    uv run python scripts/investigate_tfl_timetable.py --line elizabeth
    uv run python scripts/investigate_tfl_timetable.py --line central --validate
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import sys
from pathlib import Path

# Ensure src/ is on the path when run from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import os

import tfl.api
import tfl.models
from tfl.api._transport import get_ratelimited_client
from tfl.api.journey import get_journey_results
from tfl.api.lines import get_stop_points_by_line
from tfl.api.timetable import Direction, get_timetable
from tfl.models.timetable import StationInterval, TimetableResponse

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_stop_times(
    route_intervals: list[StationInterval],
) -> list[tuple[str, float, float]]:
    """Parse station_intervals into a list of (stop_id, arrive_min, depart_min).

    TfL encodes each stop *twice* in the intervals list: first as arrival,
    then as departure.  E.g.:
        stop_id='940GZZLUNBP'  time_to_arrival=1.0   ← train arrives
        stop_id='940GZZLUNBP'  time_to_arrival=2.0   ← train departs

    We take the first StationInterval entry (index 0 — all entries in
    station_intervals represent the same route driven at different times;
    we just want one representative).

    Returns a list ordered by position in the route.
    """
    if not route_intervals:
        return []

    # Pick a representative: the median by total journey time.
    def total_time(si: StationInterval) -> float:
        return si.intervals[-1].time_to_arrival if si.intervals else 0.0

    sorted_si = sorted(route_intervals, key=total_time)
    chosen = sorted_si[len(sorted_si) // 2]

    # Group successive entries for the same stop_id into (arrive, depart) pairs.
    stops: list[tuple[str, float, float]] = []
    prev_stop_id: str | None = None
    arrive_time: float | None = None

    for iv in chosen.intervals:
        if iv.stop_id != prev_stop_id:
            # New stop — this entry is the arrival time.
            if prev_stop_id is not None and arrive_time is not None:
                # Previous stop: we never saw a departure → use arrival as departure.
                stops.append((prev_stop_id, arrive_time, arrive_time))
            prev_stop_id = iv.stop_id
            arrive_time = iv.time_to_arrival
        else:
            # Same stop again — this is the departure time.
            assert arrive_time is not None
            stops.append((iv.stop_id, arrive_time, iv.time_to_arrival))
            prev_stop_id = None
            arrive_time = None

    # Flush trailing stop with no departure recorded.
    if prev_stop_id is not None and arrive_time is not None:
        stops.append((prev_stop_id, arrive_time, arrive_time))

    return stops


def extract_pairwise_times(
    response: TimetableResponse,
) -> dict[tuple[str, str], float]:
    """Return {(from_stop_id, to_stop_id): travel_minutes} from a TimetableResponse.

    Travel time from stop A → stop B is computed as:
        arrive_B - depart_A
    where depart_A and arrive_B come from the station_intervals cumulative times.

    The departure stop itself (response.timetable.departure_stop_id) is treated
    as departing at time 0.
    """
    if response.timetable is None:
        return {}

    departure_id = response.timetable.departure_stop_id
    times: dict[tuple[str, str], float] = {}

    for route in response.timetable.routes:
        stop_times = _parse_stop_times(route.station_intervals)
        if not stop_times:
            continue

        # Build indexed list: [(stop_id, arrive, depart), ...]
        # Prepend the departure stop at time 0.
        full: list[tuple[str, float, float]] = [(departure_id, 0.0, 0.0), *stop_times]

        # All forward pairs (i → j) where i < j.
        for i in range(len(full)):
            from_id, _, from_depart = full[i]
            for j in range(i + 1, len(full)):
                to_id, to_arrive, _ = full[j]
                travel = to_arrive - from_depart
                if travel > 0:
                    pair = (from_id, to_id)
                    if pair not in times or times[pair] > travel:
                        times[pair] = travel

    return times


async def get_timetable_for_stop(
    client,
    line_id: str,
    stop_id: str,
    app_key: str,
) -> TimetableResponse | None:
    """Try inbound then outbound; return first response with timetable data."""
    for direction in (Direction.INBOUND, Direction.OUTBOUND):
        try:
            resp = await get_timetable(client, line_id, stop_id, app_key, direction)
            if resp.timetable is not None:
                return resp
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Main investigation
# ---------------------------------------------------------------------------


async def investigate(line_id: str, validate: bool, app_key: str) -> None:
    print(f"\n=== TfL Timetable Investigation: line '{line_id}' ===\n")

    async with get_ratelimited_client() as client:
        # ------------------------------------------------------------------
        # 1. Stop points
        # ------------------------------------------------------------------
        print(f"[1] Fetching stop points for line '{line_id}' …")
        stop_points = await get_stop_points_by_line(client, line_id, app_key)

        seen_ids: set[str] = set()
        unique_stops = []
        for sp in stop_points:
            if sp.naptan_id not in seen_ids:
                seen_ids.add(sp.naptan_id)
                unique_stops.append(sp)

        n = len(unique_stops)
        print(f"    {n} unique stops.")

        jp_calls = n * (n - 1) // 2
        tt_calls = n  # worst case: one per departure stop
        print(
            f"\n    API call comparison ({n} stops):\n"
            f"      Journey Planner (current)  : {jp_calls:,}\n"
            f"      Timetable (proposed, worst) : {tt_calls:,}\n"
            f"      Reduction factor            : {jp_calls / max(tt_calls, 1):.1f}x\n"
        )

        # ------------------------------------------------------------------
        # 2. Inspect timetable structure for the first stop
        # ------------------------------------------------------------------
        first_stop = unique_stops[0]
        print(
            f"[2] Timetable structure for '{first_stop.common_name}' "
            f"({first_stop.naptan_id})"
        )
        resp = await get_timetable_for_stop(
            client, line_id, first_stop.naptan_id, app_key
        )

        if resp is None or resp.timetable is None:
            print("    No timetable data returned for first stop.")
        else:
            tt = resp.timetable
            print(f"    departure_stop_id : {tt.departure_stop_id}")
            print(f"    routes            : {len(tt.routes)}")
            for ri, route in enumerate(tt.routes[:2]):
                stop_times = _parse_stop_times(route.station_intervals)
                print(
                    f"\n    Route {ri} ({len(route.station_intervals)} interval entries):"
                )
                print("    Parsed stops (arrive_min, depart_min):")
                print(
                    f"      [departure] {tt.departure_stop_id!r:40s}  arrive=0.0  depart=0.0"
                )
                for stop_id, arr, dep in stop_times[:10]:
                    name = next(
                        (s.common_name for s in unique_stops if s.naptan_id == stop_id),
                        stop_id,
                    )
                    print(f"      {name!r:40s}  arrive={arr:.1f}  depart={dep:.1f}")
                if len(stop_times) > 10:
                    print(f"      … ({len(stop_times) - 10} more stops)")

        # ------------------------------------------------------------------
        # 3. Extract pairwise times for a sample of departure stops
        # ------------------------------------------------------------------
        print("\n[3] Extracting pairwise times from timetable for first 5 stops …")
        stop_name = {sp.naptan_id: sp.common_name for sp in unique_stops}
        all_pairs: dict[tuple[str, str], float] = {}
        tt_calls_made = 0
        sample_stops = unique_stops[:5]

        for sp in sample_stops:
            resp = await get_timetable_for_stop(client, line_id, sp.naptan_id, app_key)
            tt_calls_made += 1
            if resp is None:
                print(f"    SKIP {sp.common_name!r}: no data")
                continue
            pairs = extract_pairwise_times(resp)
            for k, v in pairs.items():
                if k not in all_pairs or all_pairs[k] > v:
                    all_pairs[k] = v

        print(f"    Timetable calls made    : {tt_calls_made}")
        print(f"    Unique pairs extracted  : {len(all_pairs)}")

        print("\n    Sample extracted pairs (first 15):")
        for (fid, tid), mins in list(all_pairs.items())[:15]:
            fn = stop_name.get(fid, fid)
            tn = stop_name.get(tid, tid)
            print(f"      {fn!r:40s} → {tn!r:40s}  {mins:.1f} min")

        # ------------------------------------------------------------------
        # 4. Optional: cross-check against Journey Planner
        # ------------------------------------------------------------------
        if validate and all_pairs:
            print("\n[4] Cross-checking sample pairs against Journey Planner …")
            arrival = tfl.api.get_next_datetime(
                datetime.time(9, 0, 0, tzinfo=datetime.UTC)
            )
            modes = [
                tfl.models.ModeId.TUBE,
                tfl.models.ModeId.OVERGROUND,
                tfl.models.ModeId.DLR,
                tfl.models.ModeId.ELIZABETH_LINE,
                tfl.models.ModeId.WALKING,
            ]

            diffs: list[float] = []
            validate_sample = [
                (fid, tid, mins)
                for (fid, tid), mins in list(all_pairs.items())[:10]
                if fid in stop_name and tid in stop_name
            ]

            for fid, tid, tt_mins in validate_sample:
                fn = stop_name.get(fid, fid)
                tn = stop_name.get(tid, tid)
                try:
                    result = await get_journey_results(
                        client=client,
                        from_location=fid,
                        to_location=tid,
                        arrival_datetime=arrival,
                        modes=modes,
                        use_multi_modal_call=False,
                        app_key=app_key,
                    )
                    if (
                        isinstance(result, tfl.models.JourneyResults)
                        and result.journeys
                    ):
                        jp_mins = min(j.duration for j in result.journeys)
                        diff = abs(jp_mins - tt_mins)
                        diffs.append(diff)
                        tag = "OK  " if diff <= 5 else "DIFF"
                        print(
                            f"    [{tag}] {fn!r:30s} → {tn!r:30s}  "
                            f"timetable={tt_mins:.1f}  JP={jp_mins}  Δ={diff:.1f}"
                        )
                    else:
                        print(f"    [SKIP] {fn!r} → {tn!r}: disambiguation/no journeys")
                except Exception as exc:
                    print(f"    [ERR ] {fn!r} → {tn!r}: {exc}")

            if diffs:
                print(
                    f"\n    Validation: {len(diffs)} pairs  "
                    f"mean|Δ|={sum(diffs) / len(diffs):.1f}  "
                    f"max|Δ|={max(diffs):.1f}  "
                    f"within_5min={sum(1 for d in diffs if d <= 5)}/{len(diffs)}"
                )

    print("\nDone.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--line", default="central", help="TfL line ID (default: central)"
    )
    parser.add_argument(
        "--validate", action="store_true", help="Cross-check against Journey Planner"
    )
    args = parser.parse_args()

    app_key = os.environ.get("FLATHUNT__TFL_API_KEY", "")
    if not app_key:
        print("Warning: FLATHUNT__TFL_API_KEY not set — may be rate-limited.")

    asyncio.run(investigate(args.line, args.validate, app_key))


if __name__ == "__main__":
    main()
