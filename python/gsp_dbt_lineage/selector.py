"""Basic dbt-style selector parsing.

Subset of dbt's full selector grammar — we support:
  - Simple FQN: `stg_orders`, `analytics.fct_orders`
  - Tag prefix: `tag:foo`
  - Resource-type: `--resource-type model` (CLI flag, not in select string)
  - Plus operators: `+stg_orders` (parents), `stg_orders+` (children) — Phase 1
    implementation honors the operators by walking parent_map / child_map
    from the manifest.
  - Multiple selectors (space-separated) act as union.
  - `--exclude` strings match using the same grammar; matched nodes are removed.

Out of scope for Phase 1:
  - Set operations (`,` for intersection)
  - State selectors (`state:modified` requires a baseline manifest, parked for v0.3.x)
  - Method-prefixed selectors beyond `tag:`
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

logger = logging.getLogger(__name__)


def select_nodes(
    nodes: dict[str, Any],
    parent_map: dict[str, list[str]] | None = None,
    child_map: dict[str, list[str]] | None = None,
    select: list[str] | None = None,
    exclude: list[str] | None = None,
    resource_types: list[str] | None = None,
) -> list[str]:
    """Return a list of node IDs that match the selectors.

    `nodes` is the manifest's `nodes` dict (id -> node). `parent_map` /
    `child_map` come from the manifest; missing maps disable +/- traversal.
    """
    parent_map = parent_map or {}
    child_map = child_map or {}

    if not select:
        selected = set(nodes.keys())
    else:
        selected = set()
        for token in select:
            selected |= _match(token, nodes, parent_map, child_map)

    if exclude:
        excluded: set[str] = set()
        for token in exclude:
            excluded |= _match(token, nodes, parent_map, child_map)
        selected -= excluded

    if resource_types:
        rts = {r.strip().lower() for r in resource_types}
        selected = {nid for nid in selected if nodes.get(nid, {}).get("resource_type", "").lower() in rts}

    return sorted(selected)


def _match(
    token: str,
    nodes: dict[str, Any],
    parent_map: dict[str, list[str]],
    child_map: dict[str, list[str]],
) -> set[str]:
    """Resolve a single selector token to a set of node IDs."""
    raw = token.strip()
    if not raw:
        return set()

    walk_parents = raw.startswith("+")
    walk_children = raw.endswith("+")
    body = raw.lstrip("+").rstrip("+")

    if body.startswith("tag:"):
        tag = body[len("tag:"):]
        base = {nid for nid, n in nodes.items() if tag in (n.get("tags") or [])}
    else:
        base = _match_fqn(body, nodes)

    out = set(base)
    if walk_parents:
        out |= _walk(base, parent_map)
    if walk_children:
        out |= _walk(base, child_map)
    return out


def _match_fqn(body: str, nodes: dict[str, Any]) -> set[str]:
    """Match a body string to node IDs by name or fqn suffix."""
    out: set[str] = set()
    needle = body.lower()
    for nid, n in nodes.items():
        if n.get("name", "").lower() == needle:
            out.add(nid)
            continue
        # Match against the dotted FQN ("project.schema.name")
        fqn_parts = n.get("fqn") or []
        if fqn_parts:
            if ".".join(fqn_parts).lower() == needle:
                out.add(nid)
                continue
            if fqn_parts[-1].lower() == needle:
                out.add(nid)
    return out


def _walk(seeds: Iterable[str], adjacency: dict[str, list[str]]) -> set[str]:
    """BFS over an adjacency map, returning the visited set (excluding seeds)."""
    seen: set[str] = set()
    stack = list(seeds)
    while stack:
        nid = stack.pop()
        for next_id in adjacency.get(nid, []) or []:
            if next_id in seen:
                continue
            seen.add(next_id)
            stack.append(next_id)
    return seen
