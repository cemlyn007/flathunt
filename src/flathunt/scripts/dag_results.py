"""Streamlit app that displays properties matching the flathunt DAG output."""

import pickle
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import yaml

import rightmove.api
import rightmove.price
from flathunt.defs.size_filtered_property_ids import _parse_display_size
from flathunt.models import FinalProperty

_DAGSTER_STORAGE = Path(".dagster/storage")
_RUN_CONFIG = Path("flathunt_run_config.yaml")


def _load_asset(name: str) -> Any:
    path = _DAGSTER_STORAGE / name
    if not path.exists():
        return None
    return pickle.loads(path.read_bytes())


def _load_run_config() -> dict:
    if _RUN_CONFIG.exists():
        return yaml.safe_load(_RUN_CONFIG.read_text())
    return {}


def _get_channel(run_config: dict) -> str:
    return (
        run_config.get("ops", {})
        .get("candidate_properties", {})
        .get("config", {})
        .get("channel", "BUY")
    )


def _get_query_labels(run_config: dict) -> list[str]:
    queries = (
        run_config.get("ops", {})
        .get("matched_property_ids", {})
        .get("config", {})
        .get("queries", [])
    )
    return [
        f"Commute {i + 1} (max {q.get('max_duration', '?')} min)"
        for i, q in enumerate(queries)
    ]


def _format_price(fp: FinalProperty, channel: str) -> str:
    if fp.price is None:
        return "N/A"
    if channel == "RENT":
        monthly = rightmove.price.normalize(fp.price)
        return f"£{monthly:,.0f}/mo" if isinstance(monthly, (int, float)) else "N/A"
    return f"£{fp.price.amount:,}"


def _format_sqm(fp: FinalProperty) -> str:
    sqm = _parse_display_size(fp.display_size) if fp.display_size else None
    if sqm is not None:
        return f"{sqm:.0f} sqm"
    if fp.extracted_sqm is not None:
        return f"{fp.extracted_sqm:.0f} sqm (extracted)"
    return "N/A"


def _format_ground_rent(fp: FinalProperty) -> str:
    if fp.annual_ground_rent is None:
        return "N/A"
    parts = [f"£{fp.annual_ground_rent:,}/yr"]
    if fp.ground_rent_review_period_in_years:
        parts.append(f"review every {fp.ground_rent_review_period_in_years}yr")
    if fp.ground_rent_percentage_increase:
        parts.append(f"+{fp.ground_rent_percentage_increase:.1f}%")
    return ", ".join(parts)


def _build_rows(
    properties: list[FinalProperty],
    channel: str,
    query_labels: list[str],
) -> list[dict]:
    rows = []
    for fp in properties:
        commutes = {
            label: (f"{d} min" if d is not None else "N/A")
            for label, d in zip(query_labels, fp.commute_durations)
        }
        rows.append(
            {
                "Address": fp.display_address,
                "Price": _format_price(fp, channel),
                "Tenure": fp.tenure_type or "N/A",
                "Lease Remaining": (
                    f"{yrl} yrs"
                    if (yrl := getattr(fp, "years_remaining_on_lease", None))
                    is not None
                    else "N/A"
                ),
                "Beds": fp.bedrooms,
                "Baths": fp.bathrooms,
                "Size": _format_sqm(fp),
                "Council Tax": fp.council_tax_band or "N/A",
                "Ground Rent": _format_ground_rent(fp),
                "Service Charge": (
                    f"£{fp.annual_service_charge:,}/yr"
                    if fp.annual_service_charge is not None
                    else "N/A"
                ),
                "URL": (
                    rightmove.api.property_url(fp.property_url)
                    if fp.property_url
                    else None
                ),
                **commutes,
            }
        )
    return rows


st.set_page_config(page_title="Flathunt Results", layout="wide")
st.title("Flathunt Results")

final_properties: list[FinalProperty] | None = _load_asset("size_filtered_property_ids")

if final_properties is None:
    st.warning(
        "Missing DAG output: size_filtered_property_ids. Run the flathunt job first."
    )
    st.stop()

run_config = _load_run_config()
channel = _get_channel(run_config)
query_labels = _get_query_labels(run_config)

st.caption(f"{len(final_properties)} properties passed all constraints")

if not final_properties:
    st.info("No properties matched the configured constraints.")
    st.stop()

rows = _build_rows(final_properties, channel, query_labels)

st.dataframe(
    pd.DataFrame(rows),
    column_config={
        "URL": st.column_config.LinkColumn("URL"),
        "Beds": st.column_config.NumberColumn("Beds"),
        "Baths": st.column_config.NumberColumn("Baths"),
    },
    use_container_width=True,
    hide_index=True,
)
