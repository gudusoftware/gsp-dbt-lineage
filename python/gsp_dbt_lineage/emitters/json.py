"""Default JSON emitter for column_lineage.json.

Determinism rules (per runbook §4.5):
- nodes sorted alphabetically by node_id
- per-node arrays (upstream_tables, downstream, columns) sorted lexicographically
- per-column upstream sorted by (table, column)
- generated_at is excluded from byte-equality test (caller passes deterministic=True)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def render(
    *,
    schema_version: str,
    generator: str,
    manifest_metadata: dict[str, Any],
    backend: dict[str, Any],
    stats: dict[str, Any],
    nodes: list[dict[str, Any]],
    deterministic: bool = False,
) -> dict[str, Any]:
    """Build the lineage doc dict, applying deterministic ordering rules."""
    sorted_nodes: list[dict[str, Any]] = []
    for node in sorted(nodes, key=lambda n: n["node_id"]):
        sorted_nodes.append(_sort_node(node))

    doc: dict[str, Any] = {
        "schema_version": schema_version,
        "generator": generator,
        "manifest_metadata": manifest_metadata,
        "backend": backend,
        "stats": stats,
        "nodes": sorted_nodes,
    }
    if not deterministic:
        doc["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return doc


def write(doc: dict[str, Any], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")


def _sort_node(node: dict[str, Any]) -> dict[str, Any]:
    out = dict(node)
    if "upstream_tables" in out and isinstance(out["upstream_tables"], list):
        out["upstream_tables"] = sorted(out["upstream_tables"])
    if "downstream" in out and isinstance(out["downstream"], list):
        out["downstream"] = sorted(out["downstream"])
    if "columns" in out and isinstance(out["columns"], list):
        cols = []
        for col in out["columns"]:
            c = dict(col)
            if isinstance(c.get("upstream"), list):
                c["upstream"] = sorted(c["upstream"], key=lambda e: (e.get("table", ""), e.get("column", "")))
            cols.append(c)
        out["columns"] = sorted(cols, key=lambda c: c.get("name", ""))
    return out
