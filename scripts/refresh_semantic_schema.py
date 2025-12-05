"""Helper to force rebuild of the semantic schema and write `metricmind_schema.json`.

This script will:
- Print the resolved schema path being used (via `SEMANTIC_SCHEMA_PATH` or default)
- Call `semantic_layer.initialize(force_refresh=True)` to rebuild the schema from BigQuery
- Report success or any exceptions

Note: Rebuilding requires BigQuery access and valid GCP credentials (e.g. set `GOOGLE_APPLICATION_CREDENTIALS`).
"""
import os
import logging
import sys

# Ensure repo root is importable
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from utils import semantic_layer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("refresh_semantic_schema")

def main():
    schema_env = os.environ.get("SEMANTIC_SCHEMA_PATH", "metricmind_schema.json")
    resolved = os.path.abspath(schema_env)
    logger.info("Resolved schema path: %s", resolved)

    # Print current table settings for transparency
    logger.info("DEFS table: %s", os.environ.get("SEMANTIC_DEFS_TABLE", "uk-dta-gsmanalytics-poc.metricmind.GSM_KPI_DEFS_TEST_V4"))
    logger.info("DATA table: %s", os.environ.get("SEMANTIC_DATA_TABLE", "uk-dta-gsmanalytics-poc.metricmind.GSM_KPI_DATA_TEST_V4"))

    # Ensure credentials present
    credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials:
        logger.warning("GOOGLE_APPLICATION_CREDENTIALS is not set; BigQuery access will fail without valid credentials.")
    else:
        logger.info("Using GOOGLE_APPLICATION_CREDENTIALS=%s", credentials)

    try:
        logger.info("Starting semantic schema rebuild (force_refresh=True)...")
        semantic_layer.initialize(force_refresh=True)
        logger.info("Rebuild attempt finished. Schema written to: %s", resolved)
    except Exception as e:
        logger.exception("Semantic schema rebuild failed: %s", e)
        sys.exit(2)

if __name__ == '__main__':
    main()
