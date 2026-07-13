import logging

import dagster as dg

import rightmove.models
from flathunt.models import FinalProperty
from rightmove.email_models import RightmoveProperty, RightmovePropertyAlert

logger = logging.getLogger(__name__)

__all__ = ["rightmove_enriched_properties"]


def _to_final_property(
    prop_listing_id: str,
    prop_address: str | None,
    prop_price_gbp: int | None,
    details_result: rightmove.models.PropertyDetailsFetchResult | None,
    extracted_sqm: float | None = None,
) -> FinalProperty:
    price: rightmove.models.Price | None = None
    if prop_price_gbp is not None:
        price = rightmove.models.Price(amount=prop_price_gbp, frequency="static")

    structured = details_result.details if details_result else None
    is_delisted = details_result.is_delisted if details_result else False

    bedrooms: int | None = None
    bathrooms: int | None = None
    display_size: str | None = None

    council_tax_band: str | None = None
    annual_ground_rent: float | None = None
    ground_rent_review_period_in_years: int | None = None
    ground_rent_percentage_increase: float | None = None
    annual_service_charge: float | None = None
    tenure_type: str | None = None
    years_remaining_on_lease: int | None = None

    latitude: float | None = None
    longitude: float | None = None

    if structured is not None:
        bedrooms = structured.bedrooms
        bathrooms = structured.bathrooms
        if structured.size_sqm is not None:
            display_size = f"{structured.size_sqm:.0f} sqm"
        lc = structured.living_costs
        council_tax_band = lc.council_tax_band
        annual_ground_rent = lc.annual_ground_rent
        ground_rent_review_period_in_years = lc.ground_rent_review_period_in_years
        ground_rent_percentage_increase = lc.ground_rent_percentage_increase
        annual_service_charge = lc.annual_service_charge
        tenure_type = structured.tenure_type
        years_remaining_on_lease = structured.years_remaining_on_lease
        if structured.location is not None:
            latitude = structured.location.latitude
            longitude = structured.location.longitude

    return FinalProperty(
        id=int(prop_listing_id),
        source="rightmove",
        display_address=prop_address or "",
        property_url=f"/properties/{prop_listing_id}",
        price=price,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        display_size=display_size,
        extracted_sqm=extracted_sqm,
        council_tax_band=council_tax_band,
        annual_ground_rent=annual_ground_rent,
        ground_rent_review_period_in_years=ground_rent_review_period_in_years,
        ground_rent_percentage_increase=ground_rent_percentage_increase,
        annual_service_charge=annual_service_charge,
        tenure_type=tenure_type,
        years_remaining_on_lease=years_remaining_on_lease,
        latitude=latitude,
        longitude=longitude,
        is_delisted=is_delisted,
    )


@dg.asset(group_name="rightmove_email")
def rightmove_enriched_properties(
    context: dg.AssetExecutionContext,
    rightmove_property_alerts: list[RightmovePropertyAlert],
    rightmove_email_property_details: dict[
        str, rightmove.models.PropertyDetailsFetchResult
    ],
) -> list[FinalProperty]:
    deduped_props: dict[str, RightmoveProperty] = {}
    for alert in rightmove_property_alerts:
        for prop in alert.properties:
            deduped_props.setdefault(prop.listing_id, prop)
    properties = list(deduped_props.values())

    if not properties:
        context.log.info("No properties across alerts; skipping enrichment.")
        context.add_output_metadata({
            "alert_count": len(rightmove_property_alerts),
            "total_count": 0,
        })
        return []

    final_properties = [
        _to_final_property(
            prop.listing_id,
            prop.address,
            prop.price_gbp,
            rightmove_email_property_details.get(prop.listing_id),
        )
        for prop in properties
    ]

    context.add_output_metadata({
        "alert_count": len(rightmove_property_alerts),
        "total_count": len(final_properties),
    })
    context.log.info(
        "Returning %d enriched Rightmove listing(s).", len(final_properties)
    )
    return final_properties
