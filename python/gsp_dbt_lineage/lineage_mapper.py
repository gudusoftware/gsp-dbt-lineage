"""Map GSP/SQLFlow JSON responses → our lineage schema (column_lineage.json).

Input shape (from `gsp-dbt-lineage`-internal API):
    response = {
        "code": 200,
        "data": {
            "sqlflow": {
                "dbobjs": {"servers": [{ name, dbVendor, databases: [{ name, schemas: [{ name, tables: [{ id, name, columns: [{id, name}], ... }] }] }]}],
                "relationships": [{ id, type ("fdd"|"fdr"|"fda"|"fdc"), target: {id, column, parentId, parentName}, sources: [...] }],
                "processes": [...]
            }
        }
    }

Output shape: see lineage_schema.py.

Mapping rules:
- Walk dbobjs to build (table_id -> fully qualified name) and (column_id -> column-name + table_id).
- For each "fdd" (Field Data Dependence) relationship, emit a column edge.
- "fdr" (Field Data Relation) is also emitted but tagged transform="control" — these
  are GROUP BY / WHERE / ORDER BY columns that participate in row selection.
- Tables with id but no resolvable name are dropped from upstream_tables (we
  never fabricate edges per C10).
- The "target" of every relationship is the result-set; we collapse to the
  outermost projection by walking to the top-level RS-N parent.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# GSP synthesizes helper columns for procedural / aggregate constructs that
# are not user-visible projections: `COUNT` (function head), `COUNT(N)` (the
# aggregate-call result-set column from `IF (SELECT COUNT(1) FROM ...)`-style
# predicates), and `RELATIONROWS` (a row-count pseudo-column GSP attaches to
# tables that participate in WHERE / ORDER BY). Dropping these matches the
# pre-existing filter for T-SQL `@`-prefixed local variables.
_GSP_SYNTHETIC_COLUMN_NAMES = {"COUNT", "RELATIONROWS"}
_GSP_SYNTHETIC_COLUMN_RE = re.compile(r"^COUNT\(\d+\)$", re.IGNORECASE)


def _is_synthetic_column(name: str) -> bool:
    if not name:
        return False
    if name.startswith("@"):
        return True
    upper = name.upper()
    if upper in _GSP_SYNTHETIC_COLUMN_NAMES:
        return True
    if _GSP_SYNTHETIC_COLUMN_RE.match(upper):
        return True
    return False


@dataclass
class _TableRef:
    table_id: str
    fqn: str
    is_real: bool  # True = actual table; False = result-set / temp / CTE
    columns_by_id: dict[str, str]  # column_id -> column_name
    columns_by_name: dict[str, str]  # column_name -> column_id


_GSP_DEFAULT_NAMES = {"DEFAULT_SERVER", "DEFAULT", "<default>", ""}


def _walk_dbobjs(dbobjs: dict[str, Any]) -> dict[str, _TableRef]:
    """Build table_id -> _TableRef map from a dbobjs payload."""
    tables: dict[str, _TableRef] = {}
    for server in dbobjs.get("servers") or []:
        server_name = server.get("name") or ""
        if server_name in _GSP_DEFAULT_NAMES:
            server_name = ""
        for db in server.get("databases") or []:
            db_name = db.get("name") or ""
            if db_name in _GSP_DEFAULT_NAMES:
                db_name = ""
            for schema in db.get("schemas") or []:
                schema_name = schema.get("name") or ""
                if schema_name in _GSP_DEFAULT_NAMES:
                    schema_name = ""
                for collection_key in ("tables", "others"):
                    for tbl in schema.get(collection_key) or []:
                        tid = str(tbl.get("id"))
                        name = tbl.get("name") or tbl.get("displayName") or ""
                        is_real = collection_key == "tables" and bool(name) and not name.startswith("RS-")
                        fqn = ".".join(p for p in (server_name, db_name, schema_name, name) if p)
                        cols_by_id: dict[str, str] = {}
                        cols_by_name: dict[str, str] = {}
                        for col in tbl.get("columns") or []:
                            cid = str(col.get("id"))
                            cname = col.get("name") or ""
                            if cid and cname:
                                cols_by_id[cid] = cname
                                cols_by_name.setdefault(cname, cid)
                        tables[tid] = _TableRef(
                            table_id=tid,
                            fqn=fqn or name or f"<id:{tid}>",
                            is_real=is_real,
                            columns_by_id=cols_by_id,
                            columns_by_name=cols_by_name,
                        )
    return tables


def _is_result_set(parent_name: str | None) -> bool:
    if not parent_name:
        return False
    return parent_name.startswith("RS-") or parent_name.startswith("ResultSet")


def _classify_relationship(rel_type: str) -> tuple[str, bool]:
    """Map GSP relationship type -> (transform_label, is_value_lineage).

    fdd = Field Data Dependence (value-carrying — actual lineage)
    fda = Field Data Aggregation (aggregate function inputs)
    fdc = Field Data Control (CASE WHEN, IF — value-carrying through control flow)
    fdr = Field Data Relation (GROUP BY / ORDER BY / WHERE — control, not value)
    """
    t = (rel_type or "").lower()
    if t == "fdd":
        return "direct", True
    if t == "fda":
        return "aggregate", True
    if t == "fdc":
        return "expression", True
    if t == "fdr":
        return "control", False
    return "unknown", True


def _extract_procedural_evidence(
    sqlflow: dict[str, Any],
    tables: dict[str, _TableRef],
) -> dict[str, Any] | None:
    """Build an evidence summary for procedural / multi-statement scripts.

    Procedural BigQuery / T-SQL scripts can write to multiple TEMP TABLE or
    real-table targets in one shot (the dbt CLL story this package solves).
    The flat node-level `columns` list collapses same-named columns across
    those write targets, which is correct for the column_lineage.json schema
    (one node = one logical projection) but loses the per-target attribution
    a reviewer needs to trust the result.

    This block records, *in addition* to the flat columns list:
      - one entry per write-target table (`temp_table`, real CREATE-TABLE-AS,
        INSERT INTO target);
      - the source real-table(s) each target was read from;
      - the column edges traced into that target;
      - process / branch counts.

    Returns ``None`` if the response shows no procedural / multi-statement
    structure (single-CTAS, single-CTE, etc.).
    """
    relationships = sqlflow.get("relationships") or []
    processes = sqlflow.get("processes") or []

    # Build target-table -> {target_col: [source_table.column, ...]}
    # by walking only fdd relationships whose target is a real (or temp) table.
    edges_by_target_table: dict[str, dict[str, list[dict[str, str]]]] = {}
    table_id_to_subtype: dict[str, str | None] = {}
    for rel in relationships:
        if (rel.get("type") or "").lower() != "fdd":
            continue
        target = rel.get("target") or {}
        target_parent_id = str(target.get("parentId", ""))
        target_parent = tables.get(target_parent_id)
        target_col = target.get("column") or ""
        if not target_parent or not target_col or not target_parent.is_real:
            continue
        if _is_synthetic_column(target_col):
            continue
        if target_col == "*":
            continue
        # Walk through the source(s); when source is a result-set, recurse one
        # hop via the result-set's own incoming fdd rels to find a real source.
        resolved_sources: list[dict[str, str]] = []
        for src in rel.get("sources") or []:
            src_parent_id = str(src.get("parentId", ""))
            src_parent = tables.get(src_parent_id)
            src_col = src.get("column") or ""
            if not src_parent or not src_col:
                continue
            if src_parent.is_real:
                resolved_sources.append({"table": src_parent.fqn, "column": src_col})
                continue
            # source is a result-set — find the inbound fdd relationship(s) for
            # (src_parent_id, src_col) and follow them one step.
            for upstream_rel in relationships:
                if (upstream_rel.get("type") or "").lower() != "fdd":
                    continue
                ut = upstream_rel.get("target") or {}
                if str(ut.get("parentId", "")) != src_parent_id:
                    continue
                if (ut.get("column") or "") != src_col:
                    continue
                for usrc in upstream_rel.get("sources") or []:
                    usrc_parent = tables.get(str(usrc.get("parentId", "")))
                    usrc_col = usrc.get("column") or ""
                    if usrc_parent and usrc_parent.is_real and usrc_col:
                        resolved_sources.append(
                            {"table": usrc_parent.fqn, "column": usrc_col}
                        )
        if not resolved_sources:
            continue
        per_table = edges_by_target_table.setdefault(target_parent.fqn, {})
        per_col = per_table.setdefault(target_col, [])
        for s in resolved_sources:
            if s not in per_col:
                per_col.append(s)
        # Track the GSP subType ("temp_table" vs None for real tables) per
        # target so the evidence block can flag temp vs persisted targets.
        for srv in (sqlflow.get("dbobjs") or {}).get("servers") or []:
            for db in srv.get("databases") or []:
                for sch in db.get("schemas") or []:
                    for t in sch.get("tables") or []:
                        if str(t.get("id")) == target_parent_id:
                            table_id_to_subtype[target_parent.fqn] = t.get("subType")

    if not edges_by_target_table:
        return None
    if len(edges_by_target_table) < 2 and len(processes) < 2:
        # Single write target and single statement — not procedural enough to
        # warrant a separate evidence block; the flat columns list already
        # captures everything.
        return None

    write_targets: list[dict[str, Any]] = []
    column_edge_count = 0
    for tgt_table in sorted(edges_by_target_table):
        per_col = edges_by_target_table[tgt_table]
        target_columns = sorted(per_col.keys())
        from_tables = sorted({s["table"] for col in per_col.values() for s in col})
        edges = [
            {"target_column": tc, "from": s}
            for tc in target_columns
            for s in sorted(per_col[tc], key=lambda x: (x["table"], x["column"]))
        ]
        column_edge_count += len(edges)
        wt: dict[str, Any] = {
            "table": tgt_table,
            "from": from_tables,
            "columns": target_columns,
            "edges": edges,
        }
        sub = table_id_to_subtype.get(tgt_table)
        if sub:
            wt["subType"] = sub
        write_targets.append(wt)

    return {
        "procedural": {
            "write_targets": write_targets,
            "write_target_count": len(write_targets),
            "column_edge_count": column_edge_count,
            "process_count": len(processes),
        }
    }


def map_gsp_to_node(
    response: dict[str, Any],
    *,
    node_id: str,
    dialect: str,
) -> dict[str, Any]:
    """Convert a GSP/SQLFlow lineage response into a single node dict.

    Used per-model. The caller assembles the final document by sorting nodes.
    """
    data = (response or {}).get("data") or {}
    sqlflow = data.get("sqlflow") or {}
    dbobjs = sqlflow.get("dbobjs") or {}
    relationships = sqlflow.get("relationships") or []

    tables = _walk_dbobjs(dbobjs)

    # 1. Identify upstream tables (real tables only — drop result-sets/temps).
    upstream_tables = sorted({t.fqn for t in tables.values() if t.is_real})

    # 2. Walk relationships to build per-target-column upstream edges.
    # The "target column" is the outermost-result-set column. The "sources"
    # are real-table columns or result-set columns that we trace back through
    # other relationships.
    columns_by_target: dict[tuple[str, str], dict[str, Any]] = {}
    unresolved: list[dict[str, Any]] = []

    for rel in relationships:
        target = rel.get("target") or {}
        sources = rel.get("sources") or []
        rel_type = rel.get("type")
        transform, is_value = _classify_relationship(rel_type)

        target_parent_id = str(target.get("parentId", ""))
        target_parent = tables.get(target_parent_id)
        target_col = target.get("column") or ""
        # Skip target columns that are wildcard '*' anchored to a real table
        # (those represent table-level edges, not column-level).
        if not target_col or not target_parent:
            continue
        if target_col == "*" and target_parent.is_real:
            continue

        # We index by (target_table_fqn, target_col) so the same column
        # accumulates edges across multiple relationships.
        # If the target sits inside a non-real result-set, record it under
        # `<target>` (the projection); the upstream column resolution still
        # walks to real tables via parentId.
        target_key = (target_parent.fqn, target_col)

        col_entry = columns_by_target.setdefault(
            target_key,
            {"name": target_col, "upstream": [], "transform": transform, "_value": is_value},
        )
        # Promote transform from `direct` to `expression` if this rel is
        # an aggregate / control — preserve the strongest classification.
        if transform != "direct" and col_entry["transform"] == "direct":
            col_entry["transform"] = transform

        for src in sources:
            src_parent_id = str(src.get("parentId", ""))
            src_parent = tables.get(src_parent_id)
            src_col = src.get("column") or ""
            if not src_parent:
                # Source not present in dbobjs — record unresolved, do not fabricate.
                unresolved.append({
                    "reason": "source_table_unknown",
                    "target_column": target_col,
                    "rel_type": rel_type,
                    "source_parent_id": src_parent_id,
                })
                continue
            if not src_col:
                continue
            if src_parent.is_real:
                edge = {"table": src_parent.fqn, "column": src_col}
                if edge not in col_entry["upstream"]:
                    col_entry["upstream"].append(edge)

    # 3. Filter to only the outermost-result-set node (the projection).
    # Heuristic: if any target table is not real, those are the projections.
    # Convert to columns list, sorted.
    columns: list[dict[str, Any]] = []
    for (target_table, target_col), entry in columns_by_target.items():
        # Determine confidence: at least one upstream → high; none → low.
        confidence = "high" if entry["upstream"] else "low"
        is_value = entry.pop("_value", True)
        if not is_value and entry["transform"] == "control":
            # Pure control-flow edges are kept but lower confidence by default.
            confidence = "medium"
        columns.append({
            "name": target_col,
            "upstream": sorted(entry["upstream"], key=lambda e: (e["table"], e["column"])),
            "transform": entry["transform"],
            "confidence": confidence,
        })
    # Deduplicate by column name when multiple result-sets project the same name —
    # union the upstream edges.
    by_name: dict[str, dict[str, Any]] = {}
    for c in columns:
        existing = by_name.get(c["name"])
        if not existing:
            by_name[c["name"]] = c
            continue
        merged = list({(e["table"], e["column"]): e for e in existing["upstream"] + c["upstream"]}.values())
        existing["upstream"] = sorted(merged, key=lambda e: (e["table"], e["column"]))
    columns = sorted(by_name.values(), key=lambda c: c["name"])

    # Drop GSP-synthetic columns that are not real output projections:
    #   - T-SQL `@`-prefixed local variables / BigQuery `@` query parameters
    #   - Aggregate-helper rows (`COUNT`, `COUNT(1)`) that GSP emits when an IF
    #     predicate contains `(SELECT COUNT(N) FROM ...)`
    #   - `RELATIONROWS` row-count pseudo-columns attached to tables in
    #     WHERE / ORDER BY clauses
    columns = [c for c in columns if not _is_synthetic_column(c["name"])]

    # 4. Status / overall confidence.
    if not columns and not upstream_tables:
        status = "unsupported"
        node_confidence = "low"
    elif columns and any(c["upstream"] for c in columns):
        status = "parsed"
        node_confidence = "high" if all(c["upstream"] for c in columns) else "medium"
    else:
        status = "partial"
        node_confidence = "low"

    node: dict[str, Any] = {
        "node_id": node_id,
        "status": status,
        "confidence": node_confidence,
        "dialect": dialect,
        "upstream_tables": upstream_tables,
        "downstream": [],   # populated by the caller from manifest child_map
        "columns": columns,
        "unresolved": unresolved,
        "warnings": [],
    }
    evidence = _extract_procedural_evidence(sqlflow, tables)
    if evidence:
        node["evidence"] = evidence
    return node
