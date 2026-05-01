"""Confidence scoring + unresolved-edge tracking.

Per ADR-007 / runbook constraint C10: never fabricate edges. Every column
gets one of {high, medium, low}. Every dropped edge gets an `unresolved` entry
describing why.

Rules (Phase 2):
  high   — every output column has ≥1 resolved upstream from a real table.
  medium — at least one column has resolved upstream, but at least one column
           has none (parser saw the column, couldn't trace its source).
  low    — no output columns have resolved upstreams (e.g. dynamic SQL,
           pure procedure-body without traceable I/O).
"""

from __future__ import annotations

from typing import Any


def compute_node_confidence(columns: list[dict[str, Any]]) -> str:
    if not columns:
        return "low"
    has_resolved = sum(1 for c in columns if c.get("upstream"))
    if has_resolved == len(columns):
        return "high"
    if has_resolved > 0:
        return "medium"
    return "low"


def annotate_dynamic_sql(
    node: dict[str, Any],
    sql: str,
) -> dict[str, Any]:
    """Detect dynamic-SQL constructs in the source and add an unresolved entry.

    Avoids deep parsing — looks for case-insensitive markers known to defeat
    static analysis (EXECUTE IMMEDIATE, sp_executesql with @sql, etc.).
    """
    upper = (sql or "").upper()
    markers = (
        ("EXECUTE IMMEDIATE", "execute_immediate"),
        ("EXEC SP_EXECUTESQL", "sp_executesql"),
        ("EXECUTE SP_EXECUTESQL", "sp_executesql"),
    )
    for marker, reason in markers:
        if marker in upper:
            node.setdefault("unresolved", []).append({
                "reason": "dynamic_sql",
                "marker": reason,
                "fragment_preview": _excerpt(sql, marker),
            })
            # Dynamic SQL caps confidence at low.
            node["confidence"] = "low"
            if node.get("status") == "parsed":
                node["status"] = "partial"
            break
    return node


def _excerpt(sql: str, marker: str, ctx: int = 40) -> str:
    if not sql:
        return ""
    idx = sql.upper().find(marker.upper())
    if idx < 0:
        return ""
    start = max(0, idx - ctx)
    end = min(len(sql), idx + len(marker) + ctx)
    return sql[start:end]
