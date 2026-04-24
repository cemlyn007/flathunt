"""Streamlit app that displays properties matching the flathunt DAG output."""

import pickle
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import yaml

import rightmove.api
import rightmove.price
from flathunt.defs.enriched_properties import _parse_display_size
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


def _build_rows(
    properties: list[FinalProperty],
    channel: str,
    query_labels: list[str],
) -> list[dict]:
    rows = []
    for fp in properties:
        commutes = dict(zip(query_labels, fp.commute_durations, strict=True))
        commute_values = [d for d in fp.commute_durations if d is not None]
        max_commute = max(commute_values) if commute_values else None

        price_value: float | None = None
        if fp.price is not None:
            if channel == "RENT":
                monthly = rightmove.price.normalize(fp.price)
                price_value = monthly if isinstance(monthly, int | float) else None
            else:
                price_value = fp.price.amount

        sqm = _parse_display_size(fp.display_size) if fp.display_size else None
        if sqm is None and fp.extracted_sqm is not None:
            sqm = fp.extracted_sqm

        rows.append({
            "Address": fp.display_address,
            "Price": price_value,
            "Tenure": fp.tenure_type or fp.extracted_tenure_type or "N/A",
            "Lease Remaining": fp.years_remaining_on_lease
            if fp.years_remaining_on_lease is not None
            else fp.extracted_years_remaining_on_lease,
            "Beds": fp.bedrooms,
            "Baths": fp.bathrooms,
            "Size": sqm,
            "Council Tax": fp.council_tax_band
            or fp.extracted_council_tax_band
            or "N/A",
            "Ground Rent": fp.annual_ground_rent
            if fp.annual_ground_rent is not None
            else fp.extracted_annual_ground_rent,
            "Service Charge": fp.annual_service_charge
            if fp.annual_service_charge is not None
            else fp.extracted_annual_service_charge,
            "Max Commute": max_commute,
            "URL": (
                rightmove.api.property_url(fp.property_url) if fp.property_url else None
            ),
            **commutes,
        })
    return rows


st.set_page_config(page_title="Flathunt Results", layout="wide")
st.title("Flathunt Results")

final_properties: list[FinalProperty] | None = _load_asset("enriched_properties")

if final_properties is None:
    st.warning("Missing DAG output: enriched_properties. Run the flathunt job first.")
    st.stop()

run_config = _load_run_config()
channel = _get_channel(run_config)
query_labels = _get_query_labels(run_config)

st.caption(f"{len(final_properties)} properties passed all constraints")

if not final_properties:
    st.info("No properties matched the configured constraints.")
    st.stop()

rows = _build_rows(final_properties, channel, query_labels)

price_label = "Price (£/mo)" if channel == "RENT" else "Price (£)"
price_format = "£%.0f/mo" if channel == "RENT" else "£%.0f"
commute_config = {
    label: st.column_config.NumberColumn(label, format="%.0f") for label in query_labels
}

st.dataframe(
    pd.DataFrame(rows),
    column_config={
        "URL": st.column_config.LinkColumn("URL"),
        "Price": st.column_config.NumberColumn(price_label, format=price_format),
        "Lease Remaining": st.column_config.NumberColumn(
            "Lease Remaining (yrs)", format="%.0f"
        ),
        "Beds": st.column_config.NumberColumn("Beds"),
        "Baths": st.column_config.NumberColumn("Baths"),
        "Size": st.column_config.NumberColumn("Size (sqm)", format="%.0f"),
        "Ground Rent": st.column_config.NumberColumn(
            "Ground Rent (£/yr)", format="£%.0f"
        ),
        "Service Charge": st.column_config.NumberColumn(
            "Service Charge (£/yr)", format="£%.0f"
        ),
        "Max Commute": st.column_config.NumberColumn(
            "Max Commute (min)", format="%.0f"
        ),
        **commute_config,
    },
    use_container_width=True,
    hide_index=True,
)
