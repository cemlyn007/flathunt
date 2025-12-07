import logging

import dotenv

from flathunt.ui import (
    render_isochrone_section,
    render_map_section,
    render_property_search_section,
    render_query_section,
    render_results_section,
)

logger = logging.getLogger("flathunt")
logging.basicConfig(level=logging.INFO)

dotenv.load_dotenv()


if __name__ == "__main__":
    render_query_section()
    render_isochrone_section()
    render_map_section()
    min_budget, max_budget = render_property_search_section()
    if min_budget is not None and max_budget is not None:
        render_results_section(min_budget, max_budget)

    logger.info("Finished execution of flathunt.py")
