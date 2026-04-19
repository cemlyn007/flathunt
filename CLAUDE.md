# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Flathunt is a UK property search and analysis tool that:
- Searches Rightmove for properties by geolocation (tile-based map scraping, no official API)
- Builds multimodal transport graphs from OSM road data + TfL API data
- Computes isochrones (reachable areas within a max commute time) using NetworkX
- Filters and enriches properties with commute times, pricing, council tax, lease info, and floor plan sizes (via Claude API)
- Provides a Dagster data pipeline and a Streamlit web UI

## Commands

**Package manager:** `uv` (see `uv.lock` for pinned deps). Two venvs: `.venv` (Python 3.13) and `.venvt` (Python 3.14t free-threaded).

**Dev tasks (via Taskfile.yml):**
```sh
task uv-sync      # Install/sync both virtual environments
task dagster      # Run Dagster dev server
task streamlit    # Run Streamlit web UI
```

**Tests:**
```sh
uv run pytest                          # Run all non-regression tests
uv run pytest tests/flathunt/          # Run a specific test directory
uv run pytest tests/flathunt/test_isochrone.py  # Run a single test file
uv run pytest -m regression            # Run regression tests only
```
Async tests use `asyncio_mode = "auto"` (pytest-asyncio). Tests mock external APIs with `AsyncMock`/`create_autospec`.

**Linting & type checking (also run automatically as pre-commit hooks):**
```sh
uv run ruff check --fix   # Lint with auto-fix
uv run ruff format        # Format
uvx ty check              # Type check (ty, not mypy)
```

Pre-commit hooks run `ruff`, `ruff-format`, `ty check`, and `pytest` (on test file changes). Run `pre-commit run --all-files` to check everything manually.

## Architecture

### Three library packages in `src/`

- **`rightmove/`** — Rightmove web scraper. No official API; uses map tile endpoints and HTML parsing. Key: `api.py` for search and `property_details.py` for enriched data.
- **`tfl/`** — Async TfL Open Data API client. Covers journey planning, lines, stops, timetables. Rate-limited with tenacity retries.
- **`flathunt/`** — Main orchestration. Imports from both above packages.

### Dagster Pipeline (`src/flathunt/defs/`)

Assets form a DAG:
```
roads_shapefile ──► roads ──┐
                             ├──► roads_and_transport ──► isochrone_intersection ──► candidate_properties ──► matched_property_ids ──► enriched_properties
tfl_network_topology ─► transport ──┘
```

- `sources.py` defines the two external `AssetSpec`s (`roads_shapefile`, `tfl_network_topology`) and the sensor `monitor_map_file_and_tfl_lines` that detects OSM file changes and TfL topology changes (polled at most every 6 hours).
- `roads.py` and `transport.py` build NetworkX graphs from their respective sources.
- `roads_and_transport.py` merges them into a unified multimodal graph.
- `isochrone_intersection.py` intersects isochrones for all configured commute destinations.
- `candidate_properties.py` finds Rightmove properties within the isochrone area.
- `enriched_properties.py` fetches full property details and calls Claude API for floor plan/description parsing.
- `definitions.py` is the Dagster entry point that wires all assets, jobs, and sensors together.
- Pipeline config lives in `flathunt_run_config.yaml`. Per-asset config schemas are in `defs/config.py`.

### Streamlit UI

`src/flathunt/scripts/flathunter.py` is the entry point. `src/flathunt/ui/components.py` has the rendering logic. The UI reads from the same SQLite cache as the pipeline.

### Caching

`src/flathunt/cache.py` — SQLite-backed `ModelCache` keyed by Pydantic model type + string key. Used for Rightmove responses and TfL journeys to avoid redundant API calls.

### Coordinate systems

`src/flathunt/geometry.py` — Utility functions for converting between WGS84 (lat/lon) and British National Grid (BNG, EPSG:27700). The road/transport graphs use BNG internally.

## Environment Variables

Required (typically in `.env`):
- `FLATHUNT__TFL_API_KEY` — TfL Open Data API key
- `FLATHUNT__QUERIES` — JSON array of `[lon, lat, max_duration_minutes]` commute destinations

Optional:
- `FLATHUNT_ROADS_FILE_PATH` — Path to OSM shapefile (default: `greater-london-251126-free/gis_osm_roads_free_1.shp`)
- `FLATHUNT__DAILY_CRON` — Dagster schedule (default: `"0 22 * * *"`)

Optional (email notifications — all required if any are set):
- `FLATHUNT__SMTP_HOST` — SMTP server hostname (e.g. `smtp.gmail.com`)
- `FLATHUNT__SMTP_PORT` — SMTP port (default: `587`)
- `FLATHUNT__SMTP_USERNAME` — SMTP login username
- `FLATHUNT__SMTP_PASSWORD` — SMTP login password / app password
- `FLATHUNT__SMTP_FROM` — From address for notification emails
- `FLATHUNT__SMTP_TO` — Recipient address for notification emails
- `FLATHUNT__STREAMLIT_HOST` / `FLATHUNT__STREAMLIT_PORT`
- `PYTHON_GIL=0` — Disable GIL for Streamlit (Python 3.14t)

## Type Checking Note

The project uses `ty` (not mypy) for type checking. The pre-commit hook is `ty-check`. When fixing type errors, use `uvx ty check` to verify. `AutomationConditionSensorDefinition` from Dagster requires a `target` parameter — check the Dagster version in `pyproject.toml` for the exact API.
