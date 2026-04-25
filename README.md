# Flat Hunt

An automated property search pipeline built on Dagster that searches Rightmove listings and filters them based on commute times using TfL transport data and isochrone analysis. The system extracts property details using LLM models, caches results in SQLite, and sends email notifications for matching properties.

## Features

* **Automated daily searches** - Scheduled Dagster pipeline runs daily to find new properties
* **Commute filtering** - Filters properties by maximum commute duration to your locations using TfL data and isochrone analysis
* **Property details extraction** - Automatically extracts and structures property information from descriptions using Claude
* **Smart caching** - SQLite-based caching to avoid redundant processing and API calls
* **Email notifications** - Sends notifications for newly matched properties
* **Transport analysis** - Integrates TfL Open Data for accurate commute calculations
* **Streamlit dashboard** - Optional web dashboard for viewing and exploring results

## Setup

### Requirements

- Python 3.12+
- A TfL API key (free from [TfL Open Data](https://tfl.gov.uk/info-for-developers/))
- A GitHub personal access token with `models:read` scope (for Claude API usage)
- (Optional) OSM shapefile for London road networks

### Installation

1. Clone the repository and install dependencies:
```bash
pip install -e .
```

2. Create a `.env` file with required variables (see `.env.example`):
```bash
FLATHUNT__TFL_API_KEY=your_tfl_api_key
GITHUB_TOKEN=your_github_token
```

3. Configure your search parameters in `flathunt_run_config.yaml`:
```yaml
ops:
  isochrone_intersection:
    config:
      queries:
        - lon: -0.1299217
          lat: 51.5194938
          max_duration: 30  # Maximum commute time in minutes
  candidate_properties:
    config:
      channel: BUY
      min_budget: 400000
      max_budget: 775000
      has_floorplans: true
      has_images: true
      min_square_meters: 75.0
  notified_properties:
    config:
      smtp_to_addresses:
        - your-email@example.com
```

## Running the Pipeline

### Start Dagster UI for development:
```bash
flathunt-dagster-dev
```
Then visit `http://localhost:3000` to view and trigger asset runs.

### Start Streamlit dashboard:
```bash
streamlit run src/flathunt/streamlit_app.py
```

### Run the complete pipeline once:
```bash
dagster job execute -f src/flathunt/definitions.py -j flathunt
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FLATHUNT__TFL_API_KEY` | Yes | TfL Open Data API key |
| `GITHUB_TOKEN` | Yes | GitHub token for Claude API calls (models:read scope) |
| `FLATHUNT__DAILY_CRON` | No | Cron schedule for pipeline (default: `0 22 * * *` - 10pm daily) |
| `FLATHUNT_ROADS_FILE_PATH` | No | Path to OSM shapefile for road network |
| `FLATHUNT__SMTP_*` | No | SMTP settings for email notifications (all or none) |
| `FLATHUNT__STREAMLIT_*` | No | Streamlit server configuration |

## Architecture

The pipeline consists of several connected assets:

- **roads_shapefile** - Loads OSM road network data
- **tfl_network_topology** - Fetches TfL transport network
- **roads & transport** - Processes geographic and transport data
- **roads_and_transport** - Combined transport graph for routing
- **isochrone_intersection** - Calculates reachable areas from your locations
- **candidate_properties** - Searches Rightmove for matching criteria
- **matched_property_ids** - Filters candidates by commute time
- **enriched_properties** - Extracts details using LLM
- **notified_properties** - Sends email notifications for new matches

Runs are triggered daily via schedule, with additional automatic runs when the transport graph is updated.
