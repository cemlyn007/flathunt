"""Flathunt main entry point for Streamlit UI.

This module serves as the primary orchestrator for the Flathunt application,
coordinating the rendering of UI components in a logical sequence.
"""

import logging

import dotenv

from flathunt.ui.components import (
    render_isochrone_section,
    render_map_section,
    render_property_search_section,
    render_query_section,
    render_results_section,
)

# Configure logging
logger = logging.getLogger("flathunt")
logging.basicConfig(level=logging.INFO)

# Load environment variables from .env file
dotenv.load_dotenv()


def main() -> None:
    """Execute the Flathunt application workflow.

    Renders the UI in the following sequence:
    1. Query section: collect commute destination queries
    2. Isochrone section: compute and cache isochrone data
    3. Map section: display isochrone and intersection polygons
    4. Property search section: fetch properties within the intersection area
    5. Results section: apply filters and display final property results
    """
    render_query_section()
    render_isochrone_section()
    render_map_section()
    render_property_search_section()
    render_results_section()
    logger.info("Finished execution of flathunt.py")


if __name__ == "__main__":
    main()
