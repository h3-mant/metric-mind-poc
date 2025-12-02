"""
Semantic layer loader + registry for Metric Mind.

This file:
- Loads a pre-generated metricmind_schema.json when available.
- Falls back to building the schema from BigQuery (without using BigQuery.to_dataframe)
  so we avoid the db-dtypes dependency.
- Exposes lookup helpers (get_kpi_list, get_kpi_def_by_name, find_kpi_by_name).
- Is defensive about missing data and designed for fast in-memory lookups by the app.
"""
import json
import logging
import os
import time
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_SCHEMA_FILE = Path(os.environ.get("SEMANTIC_SCHEMA_PATH", "metricmind_schema.json"))
_DEFS_TABLE = os.environ.get("SEMANTIC_DEFS_TABLE", "uk-dta-gsmanalytics-poc.metricmind.GSM_KPI_DEFS_TEST_V4")
_DATA_TABLE = os.environ.get("SEMANTIC_DATA_TABLE", "uk-dta-gsmanalytics-poc.metricmind.GSM_KPI_DATA_TEST_V4")
_DEFAULT_TTL = int(os.environ.get("SEMANTIC_TTL_SECONDS", 3600))
_MAX_VALUES_PER_DIM = int(os.environ.get("SEMANTIC_MAX_VALUES_PER_DIM", 200))

_lock = threading.Lock()
_cache: Dict[str, Any] = {
    "schema": None,
    "by_id": {},
    "by_name": {},  # note: keys are normalized (lowercase stripped names)
    "loaded_at": 0,
    "ttl": _DEFAULT_TTL
}


def initialize(force_refresh: bool = False, ttl_seconds: int = _DEFAULT_TTL) -> None:
    """
    Initialize semantic layer in memory. Loads from file if present; otherwise
    attempts to build from BigQuery. Uses a TTL to avoid rebuilding too often.
    """
    with _lock:
        now = time.time()
        if not force_refresh and _cache["schema"] and (now - _cache["loaded_at"] < _cache["ttl"]):
            logger.debug("Semantic layer fresh; skipping initialize")
            return

        start = time.time()
        # Try file first
        if _SCHEMA_FILE.exists():
            try:
                logger.info("Loading semantic schema from %s", _SCHEMA_FILE)
                with open(_SCHEMA_FILE, "r", encoding="utf-8") as f:
                    schema = json.load(f)
                _load_into_cache(schema, ttl_seconds)
                logger.info("Loaded semantic schema from file in %.2fs", time.time() - start)
                return
            except Exception:
                logger.exception("Failed to load semantic schema file; will attempt BigQuery build")

        # Build from BigQuery (fallback)
        try:
            logger.info("Building semantic schema from BigQuery (this may take a while)")
            schema = _build_schema_from_bigquery()
            # write file best-effort; do not fail load if write fails
            try:
                _SCHEMA_FILE.write_text(json.dumps(schema, indent=2), encoding="utf-8")
                logger.info("Wrote semantic schema to %s", _SCHEMA_FILE)
            except Exception:
                logger.debug("Could not write schema file (non-fatal)")
            _load_into_cache(schema, ttl_seconds)
            logger.info("Built semantic schema from BigQuery in %.2fs", time.time() - start)
        except Exception as e:
            logger.exception("Failed to build semantic schema from BigQuery: %s", e)


def _load_into_cache(schema: Dict[str, Any], ttl_seconds: int) -> None:
    _cache["schema"] = schema
    _cache["by_id"] = {str(k): v for k, v in (schema.get("kpis") or {}).items()}
    by_name = {}
    for k, v in _cache["by_id"].items():
        # normalize KPI name for case-insensitive lookup
        name = (v.get("kpi_name") or "").strip()
        if name:
            by_name[name.lower()] = v
    _cache["by_name"] = by_name
    _cache["loaded_at"] = time.time()
    _cache["ttl"] = ttl_seconds
    logger.info("Semantic layer loaded: %d KPIs", len(_cache["by_id"]))


def _row_to_dict(row) -> Dict[str, Any]:
    """
    Convert a BigQuery Row-like to a plain dict safely.
    """
    try:
        # row may support mapping protocol
        if isinstance(row, dict):
            return row
        # google.cloud.bigquery Row supports keys() and __getitem__
        if hasattr(row, "keys"):
            return {k: (row.get(k) if hasattr(row, "get") else getattr(row, k, None)) for k in row.keys()}
        return dict(row)
    except Exception:
        # last-resort: fallback to attr access for common fields
        d = {}
        for attr in dir(row):
            if not attr.startswith("_"):
                try:
                    d[attr] = getattr(row, attr)
                except Exception:
                    pass
        return d


def _build_schema_from_bigquery() -> Dict[str, Any]:
    """
    Build the semantic schema by querying BigQuery. This implementation avoids
    calling job.to_dataframe() to remove reliance on db-dtypes.
    """
    from google.cloud import bigquery

    client = bigquery.Client()

    # Pull defs table rows
    defs_q = f"SELECT * FROM `{_DEFS_TABLE}`"
    defs_rows = list(client.query(defs_q).result(timeout=60))

    DIM_NAME_COLS = [f"DIM{i}_NAME" for i in range(1, 7)]
    INT_PHYS_COLS = [f"INT{str(i).zfill(2)}" for i in range(1, 11)]
    FLOAT_PHYS_COLS = [f"FLOAT{str(i).zfill(2)}" for i in range(1, 7)]

    schema: Dict[str, Any] = {"kpis": {}, "globals": {"physical_columns": {
        "dimensions": [f"DIM{i}" for i in range(1, 7)],
        "int_columns": INT_PHYS_COLS,
        "float_columns": FLOAT_PHYS_COLS,
    }}}

    def get_str_from_row(row, col):
        try:
            if hasattr(row, "get"):
                val = row.get(col)
            else:
                val = getattr(row, col, None)
            if val is None:
                return ""
            return str(val).strip()
        except Exception:
            try:
                return str(row[col]).strip()
            except Exception:
                return ""

    for row in defs_rows:
        try:
            raw_kpi = get_str_from_row(row, "KPI_ID")
            if not raw_kpi:
                continue
            kpi_id = int(float(raw_kpi))
        except Exception:
            logger.debug("Skipping defs row with invalid KPI_ID")
            continue

        kpi_entry = {
            "kpi_id": kpi_id,
            "kpi_name": get_str_from_row(row, "KPI_NAME"),
            "kpi_description": get_str_from_row(row, "KPI_DESCRIPTION"),
            "dimensions": {},
            "indicators_int": [],
            "indicators_float": []
        }

        for i, dim_name_col in enumerate(DIM_NAME_COLS, start=1):
            sem_name = get_str_from_row(row, dim_name_col)
            phys_col = f"DIM{i}"
            if sem_name:
                # fetch distinct sample values from data table (bounded)
                try:
                    q = f"""
                    SELECT DISTINCT {phys_col} AS val
                    FROM `{_DATA_TABLE}`
                    WHERE KPI_ID = @kpid AND {phys_col} IS NOT NULL
                    LIMIT 100
                    """
                    job_config = bigquery.QueryJobConfig(
                        query_parameters=[bigquery.ScalarQueryParameter("kpid", "INT64", int(kpi_id))]
                    )
                    vals_rows = list(client.query(q, job_config=job_config).result(timeout=30))
                    sample_vals = []
                    for vr in vals_rows:
                        v = getattr(vr, "val", None) if hasattr(vr, "val") else (vr.get("val") if hasattr(vr, "get") else None)
                        if v is not None:
                            s = str(v).strip()
                            if s and s != "?":
                                sample_vals.append(s)
                    sample_vals = sorted(list(dict.fromkeys(sample_vals)))[:min(20, _MAX_VALUES_PER_DIM)]
                except Exception:
                    logger.debug("Failed to sample values for KPI %s col %s", kpi_id, phys_col)
                    sample_vals = []

                kpi_entry["dimensions"][sem_name] = {
                    "physical_column": phys_col,
                    "distinct_values_sample": sample_vals,
                    "distinct_count": len(sample_vals)
                }

        # Indicators: read INT and FLOAT names/agg from defs row
        for idx in range(10):
            name = get_str_from_row(row, f"INT{str(idx+1).zfill(2)}_NAME")
            agg = get_str_from_row(row, f"INT{str(idx+1).zfill(2)}_AGG")
            phys = INT_PHYS_COLS[idx]
            if name or agg:
                kpi_entry["indicators_int"].append({
                    "name": name or f"INT{idx+1}",
                    "aggregation": agg or None,
                    "physical_column": phys
                })

        for idx in range(6):
            name = get_str_from_row(row, f"FLOAT{idx+1}_NAME")
            agg = get_str_from_row(row, f"FLOAT{idx+1}_AGG")
            phys = FLOAT_PHYS_COLS[idx]
            if name or agg:
                kpi_entry["indicators_float"].append({
                    "name": name or f"FLOAT{idx+1}",
                    "aggregation": agg or None,
                    "physical_column": phys
                })

        schema["kpis"][str(kpi_id)] = kpi_entry

    return schema


def get_kpi_list(limit: int = 30, sort: bool = True) -> List[str]:
    with _lock:
        schema = _cache.get("schema") or {}
        entries = schema.get("kpis", {}) or {}
        names = [v.get("kpi_name") or f"{k}" for k, v in entries.items()]
        if sort:
            try:
                names = sorted(names, key=lambda s: (s is None, s.lower() if isinstance(s, str) else str(s)))
            except Exception:
                pass
        return names[:limit]


def get_kpi_def_by_id(kpi_id: Any) -> Optional[Dict[str, Any]]:
    with _lock:
        if kpi_id is None:
            return None
        try:
            key = str(int(kpi_id))
        except Exception:
            key = str(kpi_id)
        return _cache["by_id"].get(key)


def get_kpi_def_by_name(name: str) -> Optional[Dict[str, Any]]:
    with _lock:
        if name is None:
            return None
        return _cache["by_name"].get(name.strip().lower())


def explain_kpi(kpi_id: Any) -> str:
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


# -------------------------
# Fuzzy / wildcard KPI lookup helpers
# -------------------------
def _normalize_text(s: Optional[str]) -> str:
    if s is None:
        return ""
    import re
    s2 = str(s).lower()
    s2 = re.sub(r"[^\w\s]", " ", s2)
    s2 = re.sub(r"\s+", " ", s2).strip()
    return s2


def _token_set(s: Optional[str]):
    s2 = _normalize_text(s)
    if not s2:
        return set()
    return set(s2.split())


def _score_name_match(query: str, candidate_name: str) -> float:
    """
    Simple scoring:
      - exact substring (case-insensitive) -> 1.0
      - token overlap ratio -> tokens_in_common / tokens_in_query
    """
    q = _normalize_text(query)
    c = _normalize_text(candidate_name)
    if not q or not c:
        return 0.0
    if q in c:
        return 1.0
    q_tokens = _token_set(q)
    c_tokens = _token_set(c)
    if not q_tokens:
        return 0.0
    overlap = q_tokens.intersection(c_tokens)
    score = len(overlap) / len(q_tokens)
    return float(score)


def find_kpi_by_name(query: str, top_n: int = 5) -> List[Tuple[float, str, Dict[str, Any]]]:
    """
    Return a list of candidate KPI definitions from the loaded semantic layer
    ranked by a simple relevance score. Each item is (score:float, kpi_id:str, kpi_def:dict).
    Requires semantic layer to be loaded (initialize()).
    """
    with _lock:
        schema = _cache.get("schema") or {}
        kpis = schema.get("kpis", {}) or {}

    q = (query or "").strip()
    if not q:
        return []

    candidates: List[Tuple[float, str, Dict[str, Any]]] = []
    # Score by KPI name and also by indicator/dimension names to allow broader matches
    for kpi_id, kdef in kpis.items():
        score = 0.0
        # primary: KPI name
        name = (kdef.get("kpi_name") or "")
        score = max(score, _score_name_match(q, name))
        # check description tokens
        desc = (kdef.get("kpi_description") or "")
        score = max(score, _score_name_match(q, desc) * 0.7)
        # check indicator names (int/float)
        for ind in (kdef.get("indicators_int") or []) + (kdef.get("indicators_float") or []):
            ins = ind.get("name") or ""
            score = max(score, _score_name_match(q, ins) * 0.9)
        # check dimension names
        for dname, dmeta in (kdef.get("dimensions") or {}).items():
            score = max(score, _score_name_match(q, dname) * 0.8)
        if score > 0:
            candidates.append((score, str(kpi_id), kdef))
    # sort descending by score then by kpi_id
    candidates.sort(key=lambda x: (-x[0], x[1]))
    return candidates[:top_n]

    # Add near the bottom of utils/semantic_layer.py (after find_kpi_by_name)

def get_compact_kpi_candidates(query: str, top_n: int = 5) -> List[Dict[str, Any]]:
    """
    Return a compact, JSON-serializable list of KPI candidate dicts for use in prompts/state.
    Each dict contains only small fields: kpi_id, kpi_name, score, small list of dimensions (name, physical_column, up to 5 sample values),
    and a short list of indicators (name, physical_column).
    """
    # Ensure semantic layer loaded (no-op if already fresh)
    try:
        initialize()
    except Exception:
        logger.debug("Semantic layer initialize failed in get_compact_kpi_candidates; continuing defensively")

    candidates = find_kpi_by_name(query, top_n=top_n)
    compact = []
    for score, kpi_id, kdef in candidates:
        # compact dimensions: include only column and up to 5 sample values
        dims = []
        for dname, meta in (kdef.get("dimensions") or {}).items():
            dims.append({
                "name": dname,
                "physical_column": meta.get("physical_column"),
                "samples": (meta.get("distinct_values_sample") or [])[:5]
            })
        # compact indicators: up to 8 total
        indicators = []
        for ind in ((kdef.get("indicators_int") or []) + (kdef.get("indicators_float") or []))[:8]:
            indicators.append({
                "name": ind.get("name"),
                "physical_column": ind.get("physical_column")
            })
        compact.append({
            "kpi_id": kdef.get("kpi_id"),
            "kpi_name": kdef.get("kpi_name"),
            "score": float(score),
            "dimensions": dims,
            "indicators": indicators
        })
    return compact


def get_compact_index(max_kpis: int = 500) -> Dict[str, Dict[str, Any]]:
    """
    Return a normalized-name -> minimal metadata mapping for the top N KPIs.
    This is useful if you want to inject a small index into a system prompt (still be mindful of token size).
    """
    with _lock:
        by_id = _cache.get("by_id", {}) or {}
        items = list(by_id.items())[:max_kpis]
    out = {}
    for k, v in items:
        name = (v.get("kpi_name") or "").strip().lower()
        if not name:
            continue
        out[name] = {
            "kpi_id": v.get("kpi_id"),
            "kpi_name": v.get("kpi_name"),
            "dims": {d: {"physical_column": m.get("physical_column")} for d, m in (v.get("dimensions") or {}).items()}
        }
    return out