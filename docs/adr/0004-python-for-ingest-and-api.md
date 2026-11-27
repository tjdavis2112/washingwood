# Python for ingest, ETL and API (FastAPI)

## Status

superseded by ADR-0006 (API part only). Python is still the language for the archiver, loader and calculations.

The archiver, loader and Python-side calculations are Python, and the API was to be FastAPI, so the backend would be one language and the ESPN reference code (cwendt94/espn-api) could be read directly. ADR-0006 replaced the API with a static site.
