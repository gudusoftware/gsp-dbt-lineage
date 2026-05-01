"""OpenMetadata emitter (BETA).

Reads our column_lineage.json document and emits a JSON file in the shape of
OpenMetadata `AddLineageRequest` payloads, suitable for either:
  - `metadata` CLI bulk ingest, or
  - direct POST to `/api/v1/lineage` (one request per array element).

Reference:
  https://docs.open-metadata.org/openmetadata-apis/apis/lineage-api

This emitter is BETA in v0.x — Phase 4 will harden against a real OM instance
before promoting to stable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Map our dialect -> OpenMetadata service name fragment. Users override
# via --platform-map and via OM service config in their ingestion recipe.
DIALECT_TO_SERVICE_TYPE: dict[str, str] = {
    "dbvbigquery": "bigquery",
    "dbvsnowflake": "snowflake",
    "dbvdatabricks": "databricks",
    "dbvsparksql": "spark",
    "dbvmssql": "mssql",
    "dbvpostgresql": "postgres",
    "dbvredshift": "redshift",
    "dbvmysql": "mysql",
    "dbvoracle": "oracle",
    "dbvtrino": "trino",
    "dbvduckdb": "duckdb",
    "dbvclickhouse": "clickhouse",
    "dbvathena": "athena",
}


def _table_fqn(service: str, table: str) -> str:
    """Build an OpenMetadata-style FQN: service.<rest>.

    `table` may already contain dots (database.schema.name); we prepend the
    service name. If the user has a custom OM service name, --service-name
    overrides this.
    """
    if "." in service:
        return f"{service}.{table}"
    return f"{service}.{table}"


def emit(
    lineage_doc: dict[str, Any],
    *,
    service_name: str | None = None,
) -> list[dict[str, Any]]:
    """Convert column_lineage.json -> list of OM AddLineageRequest dicts."""
    requests = []
    for node in lineage_doc.get("nodes") or []:
        if node.get("status") not in {"parsed", "partial"}:
            continue
        dialect = node.get("dialect")
        svc = service_name or DIALECT_TO_SERVICE_TYPE.get(dialect or "", (dialect or "external").replace("dbv", ""))
        target_fqn = _table_fqn(svc, node["node_id"])
        # Column-level edges go in a single columnsLineage list per upstream.
        for upstream_table in node.get("upstream_tables") or []:
            up_fqn = _table_fqn(svc, upstream_table)
            cols_lineage: list[dict[str, Any]] = []
            for col in node.get("columns") or []:
                ups_for_col = [u for u in (col.get("upstream") or []) if u["table"] == upstream_table]
                if not ups_for_col:
                    continue
                cols_lineage.append({
                    "fromColumns": [f"{up_fqn}.{u['column']}" for u in ups_for_col],
                    "toColumn": f"{target_fqn}.{col['name']}",
                })
            req = {
                "edge": {
                    "fromEntity": {"id": up_fqn, "type": "table"},
                    "toEntity": {"id": target_fqn, "type": "table"},
                },
            }
            if cols_lineage:
                req["edge"]["lineageDetails"] = {"columnsLineage": cols_lineage}
            requests.append(req)
    return requests


def write(requests: list[dict[str, Any]], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(requests, indent=2, sort_keys=True), encoding="utf-8")
