import json
from typing import Any

import pytest

from rightmove.models import (
    Property,
    Location,
    PropertyImages,
    PropertyImage,
    ListingUpdate,
    Price,
    DisplayPrice,
    Customer,
    ProductLabel,
    LozengeModel,
    MatchingLozenges,
)
import os

example_file_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures", "example_search.json"
)
with open(example_file_path) as file:
    MOCKED_RESPONSE = json.load(file)
PROPERTIES = MOCKED_RESPONSE["properties"]


def test_multiple_properties(search_response: dict[str, Any]) -> None:
    """Test that multiple Property models can be created from the search response data"""
    # GIVEN: property data from multiple properties in the search response
    properties_data = search_response["properties"]

    # WHEN: creating Property models from the data
    property_models: list[Property] = [
        Property.model_validate(prop) for prop in properties_data
    ]

    # THEN: the correct number of models should be created
    assert len(property_models) == len(properties_data)

    # THEN: each model should contain the expected property information
    # Test some values from the second property
    assert property_models[1].id == properties_data[1]["id"]
    assert property_models[1].bedrooms == properties_data[1]["bedrooms"]
    assert property_models[1].bathrooms == properties_data[1]["bathrooms"]
    assert property_models[1].property_sub_type == properties_data[1]["propertySubType"]


@pytest.mark.parametrize(
    "property",
    PROPERTIES,
)
class TestPropertyModels:
    def test_property_model_from_search_response(
        self, property: dict[str, Any]
    ) -> None:
        """Test that a Property model can be created from the search response data"""
        # GIVEN: a property from the search response

        # WHEN: creating a Property model from the data
        property_model = Property.model_validate(property)

        # THEN: the model should be created correctly with all expected fields
        assert property_model.id == property["id"]
        assert property_model.bedrooms == property["bedrooms"]
        assert property_model.bathrooms == property["bathrooms"]
        assert property_model.summary == property["summary"]
        assert property_model.display_address == property["displayAddress"]
        assert property_model.property_sub_type == property["propertySubType"]
        assert property_model.transaction_type == property["transactionType"]
        assert (
            property_model.property_type_full_description
            == property["propertyTypeFullDescription"]
        )

        # THEN: formatted values should match expected values
        assert property_model.formatted_distance == property["formattedDistance"]
        assert property_model.formatted_branch_name == property["formattedBranchName"]

    def test_location_model(self, property: dict[str, Any]) -> None:
        """Test that a Location model can be created from search response data"""
        # GIVEN: location data from a property in the search response
        location_data = property["location"]

        # WHEN: creating a Location model from the data
        location_model = Location.model_validate(location_data)

        # THEN: the model should contain the expected location information
        assert location_model.latitude == location_data["latitude"]
        assert location_model.longitude == location_data["longitude"]

    def test_property_images_model(self, property: dict[str, Any]) -> None:
        """Test that a PropertyImages model can be created from search response data"""
        # GIVEN: property images data from the search response
        images_data = property["propertyImages"]

        # WHEN: creating a PropertyImages model from the data
        images_model = PropertyImages.model_validate(images_data)

        # THEN: the model should contain all the expected image information
        assert images_model.main_image_src == images_data["mainImageSrc"]
        assert images_model.main_map_image_src == images_data["mainMapImageSrc"]
        assert len(images_model.images) == len(images_data["images"])

        # THEN: the first image should be correctly mapped
        first_image = images_model.images[0]
        assert isinstance(first_image, PropertyImage)
        assert first_image.url == images_data["images"][0]["url"]
        assert first_image.src_url == images_data["images"][0]["srcUrl"]
        assert first_image.caption == images_data["images"][0]["caption"]

    def test_listing_update_model(self, property: dict[str, Any]) -> None:
        """Test that a ListingUpdate model can be created from search response data"""
        # GIVEN: listing update data from a property in the search response
        listing_update_data = property["listingUpdate"]

        # WHEN: creating a ListingUpdate model from the data
        listing_update_model = ListingUpdate.model_validate(listing_update_data)

        # THEN: the model should contain the expected listing update information
        assert (
            listing_update_model.listing_update_reason
            == listing_update_data["listingUpdateReason"]
        )
        assert (
            listing_update_model.listing_update_date.isoformat().replace("+00:00", "Z")
            == listing_update_data["listingUpdateDate"]
        )

    def test_price_model(self, property: dict[str, Any]) -> None:
        """Test that a Price model can be created from search response data"""
        # GIVEN: price data from a property in the search response
        price_data = property["price"]

        # WHEN: creating a Price model from the data
        price_model = Price.model_validate(price_data)

        # THEN: the model should contain the expected price information
        assert price_model.amount == price_data["amount"]
        assert price_model.frequency == price_data["frequency"]
        assert price_model.currency_code == price_data["currencyCode"]
        assert price_model.display_prices is not None
        assert len(price_model.display_prices) == len(price_data["displayPrices"])

        # THEN: the first display price should be correctly mapped
        first_display_price = price_model.display_prices[0]
        assert isinstance(first_display_price, DisplayPrice)
        assert (
            first_display_price.display_price
            == price_data["displayPrices"][0]["displayPrice"]
        )
        assert (
            first_display_price.display_price_qualifier
            == price_data["displayPrices"][0]["displayPriceQualifier"]
        )

    def test_customer_model(self, property: dict[str, Any]) -> None:
        """Test that a Customer model can be created from search response data"""
        # GIVEN: customer data from a property in the search response
        customer_data = property["customer"]

        # WHEN: creating a Customer model from the data
        customer_model = Customer.model_validate(customer_data)

        # THEN: the model should contain the expected customer information
        assert customer_model.branch_id == customer_data["branchId"]
        assert customer_model.contact_telephone == customer_data["contactTelephone"]
        assert customer_model.branch_display_name == customer_data["branchDisplayName"]
        assert customer_model.branch_name == customer_data["branchName"]
        assert customer_model.brand_trading_name == customer_data["brandTradingName"]
        assert customer_model.development == customer_data["development"]
        assert customer_model.commercial == customer_data["commercial"]
        assert customer_model.brand_plus_logo_url == customer_data["brandPlusLogoUrl"]

    def test_product_label_model(self, property: dict[str, Any]) -> None:
        """Test that a ProductLabel model can be created from search response data"""
        # GIVEN: product label data from a property in the search response
        product_label_data = property["productLabel"]

        # WHEN: creating a ProductLabel model from the data
        product_label_model = ProductLabel.model_validate(product_label_data)

        # THEN: the model should contain the expected product label information
        assert (
            product_label_model.product_label_text
            == product_label_data["productLabelText"]
        )
        assert (
            product_label_model.spotlight_label == product_label_data["spotlightLabel"]
        )

    def test_lozenge_model(self, property: dict[str, Any]) -> None:
        """Test that a LozengeModel model can be created from search response data"""
        # GIVEN: lozenge model data from a property in the search response
        lozenge_data = property["lozengeModel"]

        # WHEN: creating a LozengeModel model from the data
        lozenge_model = LozengeModel.model_validate(lozenge_data)

        # THEN: the model should contain the expected matching lozenges
        assert len(lozenge_model.matching_lozenges) == len(
            lozenge_data["matchingLozenges"]
        )

        # AND: each matching lozenge should have the correct values
        for i, lozenge in enumerate(lozenge_model.matching_lozenges):
            original_lozenge = lozenge_data["matchingLozenges"][i]
            assert isinstance(lozenge, MatchingLozenges)
            assert lozenge.type == original_lozenge["type"]
            assert lozenge.priority == original_lozenge["priority"]

        # AND: verify we can find specific lozenges by type
        if lozenge_model.matching_lozenges:
            # Get a specific lozenge type from the original data to test against
            test_type = lozenge_data["matchingLozenges"][0]["type"]

            # Find the matching lozenge in our model
            matching_lozenge = next(
                (
                    matching_lozenge
                    for matching_lozenge in lozenge_model.matching_lozenges
                    if matching_lozenge.type == test_type
                ),
                None,
            )

            # Verify we found it and its properties match
            assert matching_lozenge is not None
            assert matching_lozenge.type == test_type
            assert (
                matching_lozenge.priority
                == lozenge_data["matchingLozenges"][0]["priority"]
            )


@pytest.mark.parametrize(
    "property",
    PROPERTIES,
)
class TestPropertyModelSerialization:
    def test_property_serialization_to_json(self, property: dict[str, Any]) -> None:
        """Test that a Property model can be serialized to JSON"""
        # GIVEN: a property model created from search response data
        property_model = Property.model_validate(property)

        # WHEN: serializing the model to JSON
        json_str = property_model.model_dump_json()
        json_dict = json.loads(json_str)

        # THEN: the JSON should contain the expected data in camelCase format
        assert json_dict["id"] == property["id"]
        assert json_dict["bedrooms"] == property["bedrooms"]
        assert json_dict["bathrooms"] == property["bathrooms"]
        assert json_dict["summary"] == property["summary"]
        assert json_dict["displayAddress"] == property["displayAddress"]
        assert json_dict["propertySubType"] == property["propertySubType"]
        assert json_dict["transactionType"] == property["transactionType"]
        assert (
            json_dict["propertyTypeFullDescription"]
            == property["propertyTypeFullDescription"]
        )
        assert json_dict["formattedDistance"] == property["formattedDistance"]
        assert json_dict["formattedBranchName"] == property["formattedBranchName"]

    def test_location_serialization_to_json(self, property: dict[str, Any]) -> None:
        """Test that a Location model can be serialized to JSON"""
        # GIVEN: a location model created from search response data
        location_data = property["location"]
        location_model = Location.model_validate(location_data)

        # WHEN: serializing the model to JSON
        json_str = location_model.model_dump_json()
        json_dict = json.loads(json_str)

        # THEN: the JSON should contain the expected location data
        assert json_dict["latitude"] == location_data["latitude"]
        assert json_dict["longitude"] == location_data["longitude"]

    def test_property_images_serialization_to_json(
        self, property: dict[str, Any]
    ) -> None:
        """Test that a PropertyImages model can be serialized to JSON"""
        # GIVEN: a property images model created from search response data
        images_data = property["propertyImages"]
        images_model = PropertyImages.model_validate(images_data)

        # WHEN: serializing the model to JSON
        json_str = images_model.model_dump_json()
        json_dict = json.loads(json_str)

        # THEN: the JSON should contain the expected image data in camelCase format
        assert json_dict["mainImageSrc"] == images_data["mainImageSrc"]
        assert json_dict["mainMapImageSrc"] == images_data["mainMapImageSrc"]
        assert len(json_dict["images"]) == len(images_data["images"])

        # THEN: the first image should be correctly serialized
        first_image = json_dict["images"][0]
        assert first_image["url"] == images_data["images"][0]["url"]
        assert first_image["srcUrl"] == images_data["images"][0]["srcUrl"]
        assert first_image["caption"] == images_data["images"][0]["caption"]

    def test_listing_update_serialization_to_json(
        self, property: dict[str, Any]
    ) -> None:
        """Test that a ListingUpdate model can be serialized to JSON"""
        # GIVEN: a listing update model created from search response data
        listing_update_data = property["listingUpdate"]
        listing_update_model = ListingUpdate.model_validate(listing_update_data)

        # WHEN: serializing the model to JSON
        json_str = listing_update_model.model_dump_json()
        json_dict = json.loads(json_str)

        # THEN: the JSON should contain the expected listing update data in camelCase format
        assert (
            json_dict["listingUpdateReason"]
            == listing_update_data["listingUpdateReason"]
        )
        assert (
            json_dict["listingUpdateDate"] == listing_update_data["listingUpdateDate"]
        )

    def test_price_serialization_to_json(self, property: dict[str, Any]) -> None:
        """Test that a Price model can be serialized to JSON"""
        # GIVEN: a price model created from search response data
        price_data = property["price"]
        price_model = Price.model_validate(price_data)

        # WHEN: serializing the model to JSON
        json_str = price_model.model_dump_json()
        json_dict = json.loads(json_str)

        # THEN: the JSON should contain the expected price data in camelCase format
        assert json_dict["amount"] == price_data["amount"]
        assert json_dict["frequency"] == price_data["frequency"]
        assert json_dict["currencyCode"] == price_data["currencyCode"]
        assert len(json_dict["displayPrices"]) == len(price_data["displayPrices"])

        # THEN: the first display price should be correctly serialized
        first_display_price = json_dict["displayPrices"][0]
        assert (
            first_display_price["displayPrice"]
            == price_data["displayPrices"][0]["displayPrice"]
        )
        assert (
            first_display_price["displayPriceQualifier"]
            == price_data["displayPrices"][0]["displayPriceQualifier"]
        )

    def test_customer_serialization_to_json(self, property: dict[str, Any]) -> None:
        """Test that a Customer model can be serialized to JSON"""
        # GIVEN: a customer model created from search response data
        customer_data = property["customer"]
        customer_model = Customer.model_validate(customer_data)

        # WHEN: serializing the model to JSON
        json_str = customer_model.model_dump_json()
        json_dict = json.loads(json_str)

        # THEN: the JSON should contain the expected customer data in camelCase format
        assert json_dict["branchId"] == customer_data["branchId"]
        assert json_dict["contactTelephone"] == customer_data["contactTelephone"]
        assert json_dict["branchDisplayName"] == customer_data["branchDisplayName"]
        assert json_dict["branchName"] == customer_data["branchName"]
        assert json_dict["brandTradingName"] == customer_data["brandTradingName"]
        assert json_dict["development"] == customer_data["development"]
        assert json_dict["commercial"] == customer_data["commercial"]
        assert json_dict["brandPlusLogoUrl"] == customer_data["brandPlusLogoUrl"]

    def test_round_trip_serialization(self, property: dict[str, Any]) -> None:
        """Test a complete round-trip serialization and deserialization of a Property model"""
        # GIVEN: a property model created from search response data
        original_model = Property.model_validate(property)

        # WHEN: serializing the model to JSON and then deserializing back to a model
        json_str = original_model.model_dump_json()
        deserialized_model = Property.model_validate_json(json_str)

        # THEN: the deserialized model should equal the original model
        assert deserialized_model == original_model

        # THEN: key properties should match
        assert deserialized_model.id == original_model.id
        assert deserialized_model.bedrooms == original_model.bedrooms
        assert deserialized_model.bathrooms == original_model.bathrooms
        assert deserialized_model.summary == original_model.summary
        assert deserialized_model.display_address == original_model.display_address
        assert deserialized_model.property_sub_type == original_model.property_sub_type
