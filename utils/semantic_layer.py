"""
Semantic layer loader + registry for Metric Mind.

Behavior:
- If metricmind_schema.json exists in the repo directory, load it (fast).
- Otherwise build the schema from BigQuery (cautious: may be slow / heavy).
- Caches the schema in-memory with a TTL. Exposes simple lookup methods used by agents.

API:
- initialize(force_refresh: bool=False, ttl_seconds: int=3600)
- get_kpi_list() -> list[str]
- get_kpi_def_by_id(kpi_id) -> dict | None
- get_kpi_def_by_name(name) -> dict | None
- explain_kpi(kpi_id) -> str
"""
import json
import logging
import os
import time
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Defaults / config
_SCHEMA_FILE = Path(os.environ.get("SEMANTIC_SCHEMA_PATH", "metricmind_schema.json"))
_DEFS_TABLE = os.environ.get("SEMANTIC_DEFS_TABLE", "uk-dta-gsmanalytics-poc.metricmind.GSM_KPI_DEFS_TEST_V4")
_DATA_TABLE = os.environ.get("SEMANTIC_DATA_TABLE", "uk-dta-gsmanalytics-poc.metricmind.GSM_KPI_DATA_TEST_V4")
_DEFAULT_TTL = int(os.environ.get("SEMANTIC_TTL_SECONDS", 3600))
_MAX_VALUES_PER_DIM = int(os.environ.get("SEMANTIC_MAX_VALUES_PER_DIM", 200))

_lock = threading.Lock()
_cache: Dict[str, Any] = {
    "schema": None,
    "by_id": {},
    "by_name": {},
    "loaded_at": 0,
    "ttl": _DEFAULT_TTL
}

def initialize(force_refresh: bool = False, ttl_seconds: int = _DEFAULT_TTL) -> None:
    """
    Initialize the semantic registry. Safe to call repeatedly.
    If _SCHEMA_FILE exists, loads it; otherwise attempts to build from BigQuery (may be slow).
    """
    with _lock:
        now = time.time()
        if not force_refresh and _cache["schema"] and (now - _cache["loaded_at"] < _cache["ttl"]):
            logger.debug("Semantic layer is fresh; skipping initialize")
            return

        # Try local file first (fast)
        if _SCHEMA_FILE.exists():
            try:
                logger.info("Loading semantic schema from %s", _SCHEMA_FILE)
                with open(_SCHEMA_FILE, "r", encoding="utf-8") as f:
                    schema = json.load(f)
                _load_into_cache(schema, ttl_seconds)
                return
            except Exception:
                logger.exception("Failed to load semantic schema file; will attempt BigQuery build")

        # Fallback: build from BigQuery (heavy)
        try:
            logger.info("Building semantic schema from BigQuery (this may take a while)")
            schema = _build_schema_from_bigquery()
            # Save a local copy for faster future loads
            try:
                _SCHEMA_FILE.write_text(json.dumps(schema, indent=2), encoding="utf-8")
                logger.info("Wrote semantic schema to %s", _SCHEMA_FILE)
            except Exception:
                logger.debug("Could not write schema file (non-fatal)")

            _load_into_cache(schema, ttl_seconds)
        except Exception as e:
            logger.exception("Failed to build semantic schema from BigQuery: %s", e)
            # leave cache as-is (possibly empty)

def _load_into_cache(schema: Dict[str, Any], ttl_seconds: int) -> None:
    _cache["schema"] = schema
    _cache["by_id"] = {k: v for k, v in (schema.get("kpis") or {}).items()}
    # Build name index
    by_name = {}
    for k, v in _cache["by_id"].items():
        name = (v.get("kpi_name") or "").strip()
        if name:
            by_name[name] = v
    _cache["by_name"] = by_name
    _cache["loaded_at"] = time.time()
    _cache["ttl"] = ttl_seconds
    logger.info("Semantic layer loaded: %d KPIs", len(_cache["by_id"]))

def _build_schema_from_bigquery() -> Dict[str, Any]:
    """
    Construct schema using BigQuery. This function follows the approach you shared,
    but is somewhat defensive: we will attempt to reduce memory usage by limiting
    samples and using queries rather than full table dumps where reasonable.
    """
    from google.cloud import bigquery
    import pandas as pd

    client = bigquery.Client()

    # Fetch defs table fully (small) if possible
    defs_q = f"SELECT * FROM `{_DEFS_TABLE}`"
    defs_df = client.query(defs_q).to_dataframe()

    # Find KPI IDs to sample from data table
    kpi_ids = defs_df["KPI_ID"].dropna().unique().tolist()

    # To avoid pulling entire data table, we get distinct values per KPI for DIM cols via targeted queries.
    DIM_NAME_COLS = [f"DIM{i}_NAME" for i in range(1,7)]
    DIM_PHYS_COLS = [f"DIM{i}" for i in range(1,7)]
    INT_PHYS_COLS = [f"INT{str(i).zfill(2)}" for i in range(1,11)]
    FLOAT_PHYS_COLS = [f"FLOAT{str(i).zfill(2)}" for i in range(1,7)]

    schema = {"kpis": {}, "globals": {"physical_columns": {
        "dimensions": DIM_PHYS_COLS,
        "int_columns": INT_PHYS_COLS,
        "float_columns": FLOAT_PHYS_COLS,
    }}}

    def _get_distinct_sample(kpi_id: int, phys_col: str, max_vals: int = _MAX_VALUES_PER_DIM):
        try:
            q = f"""
            SELECT DISTINCT {phys_col} as val
            FROM `{_DATA_TABLE}`
            WHERE KPI_ID = @kpid AND {phys_col} IS NOT NULL
            LIMIT {max_vals}
            """
            job_config = bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("kpid","INT64", int(kpi_id))]
            )
            rows = list(client.query(q, job_config=job_config).result(timeout=30))
            vals = [r.val for r in rows if hasattr(r, "val")]
            # simple sanitization
            vals = [str(v) for v in vals if v is not None and str(v).strip() and str(v) != "?"]
            return vals[:max_vals]
        except Exception:
            return []

    def get_str(row, col):
        val = row.get(col)
        return str(val).strip() if val and not pd.isna(val) else ""

    # Build entries
    for _, row in defs_df.iterrows():
        try:
            kpi_id = int(float(get_str(row, "KPI_ID")))
        except Exception:
            continue
        kpi_entry = {
            "kpi_id": kpi_id,
            "kpi_name": get_str(row, "KPI_NAME"),
            "kpi_description": get_str(row, "KPI_DESCRIPTION"),
            "dimensions": {},
            "indicators_int": [],
            "indicators_float": []
        }

        # Dimensions (semantic name -> physical col and sample)
        for i, dim_name_col in enumerate(DIM_NAME_COLS, start=1):
            sem_name = get_str(row, dim_name_col)
            phys_col = f"DIM{i}"
            if sem_name:
                sample_vals = _get_distinct_sample(kpi_id, phys_col, max_vals=20)
                kpi_entry["dimensions"][sem_name] = {
                    "physical_column": phys_col,
                    "distinct_values_sample": sample_vals,
                    "distinct_count": len(sample_vals)  # approximate
                }

        # INT indicators
        for idx in range(10):
            phys = INT_PHYS_COLS[idx]
            name = get_str(row, f"INT{str(idx+1).zfill(2)}_NAME")
            agg = get_str(row, f"INT{str(idx+1).zfill(2)}_AGG")
            if name or agg:
                kpi_entry["indicators_int"].append({
                    "name": name or f"INT{idx+1}",
                    "aggregation": agg or None,
                    "physical_column": phys
                })

        # FLOAT indicators
        for idx in range(6):
            phys = FLOAT_PHYS_COLS[idx]
            name = get_str(row, f"FLOAT{idx+1}_NAME")
            agg = get_str(row, f"FLOAT{idx+1}_AGG")
            if name or agg:
                kpi_entry["indicators_float"].append({
                    "name": name or f"FLOAT{idx+1}",
                    "aggregation": agg or None,
                    "physical_column": phys
                })

        schema["kpis"][str(kpi_id)] = kpi_entry

    return schema

def get_kpi_list() -> List[str]:
    """
    Return a short list of KPI names (strings). Keep it short and stable.
    """
    with _lock:
        schema = _cache.get("schema") or {}
        entries = schema.get("kpis", {}) or {}
        # return names, limit to a reasonable number for prompts
        names = [v.get("kpi_name") or f"{k}" for k, v in entries.items()]
        return names

def get_kpi_def_by_id(kpi_id: Any) -> Optional[Dict[str, Any]]:
    with _lock:
        return _cache["by_id"].get(str(kpi_id)) or _cache["by_id"].get(int(kpi_id)) if kpi_id is not None else None

def get_kpi_def_by_name(name: str) -> Optional[Dict[str, Any]]:
    with _lock:
        return _cache["by_name"].get(name)

def explain_kpi(kpi_id: Any) -> str:
    """
    Return a compact, human-readable explanation for one KPI.
    """
    k = get_kpi_def_by_id(kpi_id)
    if not k:
        return f"KPI {kpi_id} not found."
    lines = [f"{k.get('kpi_name')} (ID {k.get('kpi_id')})"]
    desc = k.get("kpi_description")
    if desc:
        lines.append(f"Description: {desc}")
    dims = k.get("dimensions") or {}
    if dims:
        lines.append("Dimensions:")
        for dname, meta in dims.items():
            col = meta.get("physical_column")
            cnt = meta.get("distinct_count", "?")
            lines.append(f" - {dname} (column {col}, ~{cnt} values)")
    ints = k.get("indicators_int", [])
    if ints:
        lines.append("Measures:")
        for ind in ints:
            lines.append(f" - {ind.get('name')} (col {ind.get('physical_column')})")
    return "\n".join(lines)