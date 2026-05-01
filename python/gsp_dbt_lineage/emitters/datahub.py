"""DataHub MCP (Metadata Change Proposal) emitter.

Reads our column_lineage.json document and emits a JSON file ingestable by
the standard `datahub ingest -c <recipe>` flow with `source.type: file`.

We emit MCPs (not direct REST writes) so the operator chooses when/where to
ingest. The MCP shape mirrors what the DataHub `dbt` ingestion source produces
for `upstream_lineage`, augmented with column-level edges.

Reference: https://datahubproject.io/docs/metadata-ingestion/source_docs/file
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# DataHub URN format for datasets is:
#   urn:li:dataset:(urn:li:dataPlatform:<platform>,<name>,<env>)
# We map dialect → platform via this dict; users can override via
# `--platform-map dialect=platform`.
DIALECT_TO_PLATFORM: dict[str, str] = {
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


def dialect_to_platform(dialect: str | None) -> str:
    if not dialect:
        return "external"
    return DIALECT_TO_PLATFORM.get(dialect, dialect.replace("dbv", "") or "external")


def dataset_urn(platform: str, name: str, env: str = "PROD") -> str:
    return f"urn:li:dataset:(urn:li:dataPlatform:{platform},{name},{env})"


def schema_field_urn(dataset: str, column: str) -> str:
    return f"urn:li:schemaField:({dataset},{column})"


def emit(
    lineage_doc: dict[str, Any],
    *,
    env: str = "PROD",
    platform_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Convert column_lineage.json -> list of MCPs (one per node)."""
    pmap = dict(DIALECT_TO_PLATFORM)
    if platform_map:
        pmap.update(platform_map)

    mcps: list[dict[str, Any]] = []
    for node in lineage_doc.get("nodes") or []:
        if node.get("status") not in {"parsed", "partial"}:
            continue
        dialect = node.get("dialect")
        platform = pmap.get(dialect or "", dialect_to_platform(dialect))
        # Use the full dbt node_id ("model.demo.x", "snapshot.demo.x", "seed...")
        # so we never collide a model URN with a snapshot URN that share the
        # same final segment.
        target = dataset_urn(platform, node["node_id"], env)

        upstreams = []
        for upstream_table in node.get("upstream_tables") or []:
            upstreams.append({
                "auditStamp": {"time": 0, "actor": "urn:li:corpuser:gsp-dbt-lineage"},
                "dataset": dataset_urn(platform, upstream_table, env),
                "type": "TRANSFORMED",
            })

        fine_grained = []
        for col in node.get("columns") or []:
            for up in col.get("upstream") or []:
                fine_grained.append({
                    "upstreamType": "FIELD_SET",
                    "upstreams": [schema_field_urn(dataset_urn(platform, up["table"], env), up["column"])],
                    "downstreamType": "FIELD",
                    "downstreams": [schema_field_urn(target, col["name"])],
                    "transformOperation": col.get("transform", "direct"),
                })

        mcp = {
            "entityType": "dataset",
            "entityUrn": target,
            "changeType": "UPSERT",
            "aspectName": "upstreamLineage",
            "aspect": {
                "json": {
                    "upstreams": upstreams,
                    "fineGrainedLineages": fine_grained,
                }
            },
            "systemMetadata": {
                "lastObserved": 0,
                "runId": "gsp-dbt-lineage",
                "registryName": "gsp-dbt-lineage",
                "registryVersion": lineage_doc.get("generator", "unknown"),
            },
        }
        mcps.append(mcp)
    return mcps


def write(mcps: list[dict[str, Any]], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # DataHub file source accepts a JSON array of MCPs.
    p.write_text(json.dumps(mcps, indent=2, sort_keys=True), encoding="utf-8")
