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


def main() -> None:
    render_query_section()
    render_isochrone_section()
    render_map_section()
    render_property_search_section()
    render_results_section()
    logger.info("Finished execution of flathunt.py")


if __name__ == "__main__":
    main()
