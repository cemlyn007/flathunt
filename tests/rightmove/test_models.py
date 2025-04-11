from typing import Any

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
)


class TestPropertyModel:
    def test_property_model_from_search_response(
        self, search_response: dict[str, Any]
    ) -> None:
        """Test that a Property model can be created from the search response data"""
        # GIVEN: a property from the search response
        property_data = search_response["properties"][0]

        # WHEN: creating a Property model from the data
        property_model = Property.model_validate(property_data)

        # THEN: the model should be created correctly with all expected fields
        assert property_model.id == property_data["id"]
        assert property_model.bedrooms == property_data["bedrooms"]
        assert property_model.bathrooms == property_data["bathrooms"]
        assert property_model.summary == property_data["summary"]
        assert property_model.display_address == property_data["displayAddress"]
        assert property_model.property_sub_type == property_data["propertySubType"]
        assert property_model.transaction_type == property_data["transactionType"]
        assert (
            property_model.property_type_full_description
            == property_data["propertyTypeFullDescription"]
        )

        # THEN: formatted values should match expected values
        assert property_model.formatted_distance == property_data["formattedDistance"]
        assert (
            property_model.formatted_branch_name == property_data["formattedBranchName"]
        )

    def test_location_model(self, search_response: dict[str, Any]) -> None:
        """Test that a Location model can be created from search response data"""
        # GIVEN: location data from a property in the search response
        location_data = search_response["properties"][0]["location"]

        # WHEN: creating a Location model from the data
        location_model = Location.model_validate(location_data)

        # THEN: the model should contain the expected location information
        assert location_model.latitude == location_data["latitude"]
        assert location_model.longitude == location_data["longitude"]

    def test_property_images_model(self, search_response: dict[str, Any]) -> None:
        """Test that a PropertyImages model can be created from search response data"""
        # GIVEN: property images data from the search response
        images_data = search_response["properties"][0]["propertyImages"]

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

    def test_listing_update_model(self, search_response: dict[str, Any]) -> None:
        """Test that a ListingUpdate model can be created from search response data"""
        # GIVEN: listing update data from a property in the search response
        listing_update_data = search_response["properties"][0]["listingUpdate"]

        # WHEN: creating a ListingUpdate model from the data
        listing_update_model = ListingUpdate.model_validate(listing_update_data)

        # THEN: the model should contain the expected listing update information
        assert (
            listing_update_model.listing_update_reason
            == listing_update_data["listingUpdateReason"]
        )
        assert (
            listing_update_model.listing_update_date
            == listing_update_data["listingUpdateDate"]
        )

    def test_price_model(self, search_response: dict[str, Any]) -> None:
        """Test that a Price model can be created from search response data"""
        # GIVEN: price data from a property in the search response
        price_data = search_response["properties"][0]["price"]

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

    def test_customer_model(self, search_response: dict[str, Any]) -> None:
        """Test that a Customer model can be created from search response data"""
        # GIVEN: customer data from a property in the search response
        customer_data = search_response["properties"][0]["customer"]

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

    def test_product_label_model(self, search_response: dict[str, Any]) -> None:
        """Test that a ProductLabel model can be created from search response data"""
        # GIVEN: product label data from a property in the search response
        product_label_data = search_response["properties"][0]["productLabel"]

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

    def test_lozenge_model(self, search_response: dict[str, Any]) -> None:
        """Test that a LozengeModel model can be created from search response data"""
        # GIVEN: lozenge model data from a property in the search response
        lozenge_data = search_response["properties"][0]["lozengeModel"]

        # WHEN: creating a LozengeModel model from the data
        lozenge_model = LozengeModel.model_validate(lozenge_data)

        # THEN: the model should contain the expected matching lozenges
        assert len(lozenge_model.matching_lozenges) == len(
            lozenge_data["matchingLozenges"]
        )

    def test_multiple_properties(self, search_response: dict[str, Any]) -> None:
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
        assert (
            property_models[1].property_sub_type
            == properties_data[1]["propertySubType"]
        )
