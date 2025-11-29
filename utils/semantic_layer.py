# Save as utils/semantic_layer.py

import json
import os
from typing import Dict, Any, Optional

try:
    import pandas as pd
    from google.cloud import bigquery
except Exception:
    pd = None
    bigquery = None


class SemanticLayer:
    """
    Loads KPI definitions from BigQuery (or an iterable / DataFrame),
    builds a mapping keyed by KPI_ID and exposes fast lookups and
    a compact serializer for including in LLM prompts.

    By default this targets the definitions table:
      project_id:  uk-dta-gsmanalytics-poc
      dataset_id:  metricmind
      table_name:  GSM_KPI_DEFS_TEST_V4

    You can override by passing project_table as a full path or by setting
    the SEMANTIC_LAYER_TABLE env var to a fully-qualified table.
    """

    # Default explicit values you asked for
    DEFAULT_PROJECT_ID = "uk-dta-gsmanalytics-poc"
    DEFAULT_DATASET_ID = "metricmind"
    DEFAULT_TABLE_NAME = "GSM_KPI_DEFS_TEST_V4"

    # Minimal columns expected to consider this the "definitions" table
    REQUIRED_COLUMNS = {
        "KPI_ID",
        "KPI_NAME",
        # at least one DIMn_NAME and INT01_NAME should exist; we check a subset
        "DIM1_NAME",
        "INT01_NAME",
    }

    def __init__(self):
        # semantic mapping: {kpi_id: { 'KPI_NAME': str, 'DIMENSIONS': {...}, 'METRICS': {...} } }
        self._mapping: Dict[str, Dict[str, Any]] = {}
        self.loaded = False
        self.cache_path: Optional[str] = None
        self.source_table: Optional[str] = None

    def generate_from_dataframe(self, df: "pd.DataFrame"):
        if pd is None:
            raise RuntimeError("pandas is required to call generate_from_dataframe()")

        mapping: Dict[str, Dict[str, Any]] = {}
        for _, row in df.iterrows():
            kpi_id = row.get("KPI_ID")
            if pd.isna(kpi_id):
                continue
            kpi_id = str(kpi_id)
            kpi_name = row.get("KPI_NAME", "")

            dimensions = {
                f"DIM{i}": row.get(f"DIM{i}_NAME")
                for i in range(1, 7)
                if pd.notna(row.get(f"DIM{i}_NAME"))
            }

            metrics: Dict[str, Dict[str, Any]] = {}
            for i in range(1, 11):
                name_col = f"INT{str(i).zfill(2)}_NAME"
                agg_col = f"INT{str(i).zfill(2)}_AGG"
                if pd.notna(row.get(name_col)):
                    metrics[f"INT{str(i).zfill(2)}"] = {
                        "name": row.get(name_col),
                        "aggregation": row.get(agg_col),
                    }

            for i in range(1, 7):
                name_col = f"FLOAT{i}_NAME"
                agg_col = f"FLOAT{i}_AGG"
                if pd.notna(row.get(name_col)):
                    metrics[f"FLOAT{str(i)}"] = {
                        "name": row.get(name_col),
                        "aggregation": row.get(agg_col),
                    }

            mapping[kpi_id] = {"KPI_NAME": kpi_name, "DIMENSIONS": dimensions, "METRICS": metrics}

        self._mapping = mapping
        self.loaded = True

    def _validate_definitions_df(self, df: "pd.DataFrame", raise_on_missing: bool = True) -> bool:
        """
        Basic validation to ensure the dataframe looks like the definitions table.
        Returns True if it looks valid; otherwise False (or raises if raise_on_missing).
        """
        cols = set(df.columns)
        missing = self.REQUIRED_COLUMNS - cols
        if missing:
            if raise_on_missing:
                raise ValueError(
                    f"Loaded table is missing expected definition columns: {sorted(missing)}. "
                    "Please check SEMANTIC_LAYER_TABLE and ensure you passed the definitions table."
                )
            return False
        return True

    def _build_default_project_table(self) -> str:
        """
        Build a backticked fully-qualified table path from defaults.
        """
        return f"`{self.DEFAULT_PROJECT_ID}.{self.DEFAULT_DATASET_ID}.{self.DEFAULT_TABLE_NAME}`"

    def generate_from_bigquery(
        self,
        project_table: Optional[str] = None,
        client: Optional["bigquery.Client"] = None,
    ) -> None:
        """
        Query BigQuery and build the mapping.

        Resolution order:
        1) project_table argument if provided
        2) SEMANTIC_LAYER_TABLE env var if set
        3) built-in default of uk-dta-gsmanalytics-poc.metricmind.GSM_KPI_DEFS_TEST_V4
        """
        if bigquery is None or pd is None:
            raise RuntimeError("google-cloud-bigquery and pandas are required for generate_from_bigquery()")

        project_table = project_table or os.environ.get("SEMANTIC_LAYER_TABLE") or self._build_default_project_table()
        client = client or bigquery.Client()
        query = f"SELECT * FROM {project_table}"
        df = client.query(query).to_dataframe()

        # Validate we actually queried the definitions table
        self._validate_definitions_df(df)

        # store source for audit/debugging
        self.source_table = project_table
        self.generate_from_dataframe(df)

    def generate_from_definitions_table(self, client: Optional["bigquery.Client"] = None) -> None:
        """
        Convenience wrapper that reads the table name from SEMANTIC_LAYER_TABLE env var
        or falls back to the default built-in path.
        """
        return self.generate_from_bigquery(project_table=None, client=client)

    def save_cache(self, path: str) -> None:
        # Save mapping + metadata (source table)
        self.cache_path = path
        payload = {"_source_table": self.source_table, "mapping": self._mapping}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

    def load_cache(self, path: str) -> None:
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        # support older cache format where only mapping was saved
        if isinstance(payload, dict) and "mapping" in payload:
            self._mapping = payload.get("mapping", {})
            self.source_table = payload.get("_source_table")
        else:
            self._mapping = payload
            self.source_table = None
        self.cache_path = path
        self.loaded = True

    def get_kpi(self, kpi_id: str) -> Optional[Dict[str, Any]]:
        return self._mapping.get(str(kpi_id))

    def get_dimensions_for_kpi(self, kpi_id: str) -> Dict[str, str]:
        k = self.get_kpi(kpi_id)
        return k.get("DIMENSIONS", {}) if k else {}

    def get_metrics_for_kpi(self, kpi_id: str) -> Dict[str, Dict[str, Any]]:
        k = self.get_kpi(kpi_id)
        return k.get("METRICS", {}) if k else {}

    def to_system_prompt(self, max_chars: int = 2000) -> str:
        parts = []
        chars = 0
        for kpi_id, data in self._mapping.items():
            header = f"KPI {kpi_id}: {data.get('KPI_NAME','')}"
            dims = data.get("DIMENSIONS", {})
            metrics = data.get("METRICS", {})
            dim_lines = ", ".join(f"{k}:{v}" for k, v in list(dims.items())[:6])
            metric_lines = ", ".join(f"{k}:{v.get('name')}" for k, v in list(metrics.items())[:6])
            block = f"{header}\n  DIMENSIONS: {dim_lines}\n  METRICS: {metric_lines}\n"
            if chars + len(block) > max_chars:
                break
            parts.append(block)
            chars += len(block)

        if not parts:
            return ""
        header = "DEFINITIONS: mapping of KPIs -> dimensions and metrics (truncated):\n"
        return header + "\n".join(parts)

    def size(self) -> int:
        return len(self._mapping)