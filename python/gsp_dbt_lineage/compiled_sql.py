"""Extract compiled SQL by node from a dbt manifest.

Two paths:
  1. Read from manifest's per-node `compiled_code` field (dbt 1.5+ standard).
  2. Fallback to filesystem `target/compiled/<project>/<path>` if compiled_code
     is missing or empty (some dbt setups skip embedding compiled SQL in the
     manifest to save size).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_compiled_sql(node: dict[str, Any], target_dir: Path | None = None) -> str | None:
    """Return the compiled SQL for a manifest node, or None if unavailable.

    `node` is the manifest entry (a dict from manifest.json `nodes[node_id]`).
    `target_dir` is the dbt project's `target/` path; used for fallback reads.

    Returns None for non-SQL nodes (snapshots that compile to YAML, seeds, tests
    without bodies). Caller decides whether None is "skip" or "fail".
    """
    sql = node.get("compiled_code") or node.get("compiled_sql")
    if sql:
        return sql

    if target_dir is None:
        return None

    # Fallback: target/compiled/<project>/<original_file_path>
    compiled_path_rel = node.get("compiled_path")
    if not compiled_path_rel:
        return None
    p = (target_dir / compiled_path_rel) if not Path(compiled_path_rel).is_absolute() else Path(compiled_path_rel)
    if p.is_file():
        try:
            return p.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("failed to read compiled SQL at %s: %s", p, e)
    return None


def is_eligible_for_lineage(node: dict[str, Any]) -> tuple[bool, str | None]:
    """Decide whether a node is in scope for column-lineage extraction.

    Returns (eligible, skip_reason). skip_reason is None if eligible.
    """
    rt = node.get("resource_type")
    if rt in {"model", "snapshot", "incremental"}:
        return True, None
    if rt == "seed":
        return False, "seed (no SQL body)"
    if rt == "test":
        return False, "test (data-test, not data-flow)"
    if rt == "operation":
        return False, "run-operation (out-of-band)"
    if rt is None:
        return False, "missing resource_type"
    return False, f"unsupported resource_type {rt!r}"
