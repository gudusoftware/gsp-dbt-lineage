"""Defensive readers for dbt artifacts (manifest, catalog, run_results).

Supports dbt-core 1.5 through 1.8. Schema version is detected from the
artifact's `metadata.dbt_schema_version` URL; unknown schema versions are
accepted and logged, not rejected — we want to keep working when dbt-core
adds new fields, only failing on actually-missing required fields.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Known manifest schema versions across dbt-core minors. Used only for
# logging — readers do not reject unknown versions.
KNOWN_MANIFEST_SCHEMAS = {
    "v9": "1.5",
    "v10": "1.6",
    "v11": "1.7",
    "v12": "1.8",
}


class ArtifactError(Exception):
    """Raised when a dbt artifact is missing or structurally unreadable."""


@dataclass
class ManifestMetadata:
    dbt_version: str
    dbt_schema_version: str
    project_name: str
    adapter_type: str | None
    generated_at: str | None


@dataclass
class Manifest:
    """Thin wrapper over manifest.json. Holds the raw dict + parsed metadata.

    We intentionally do NOT model the full manifest as typed structures —
    dbt-core changes manifest fields between minors and we want to be tolerant.
    """

    metadata: ManifestMetadata
    raw: dict[str, Any]

    @property
    def nodes(self) -> dict[str, Any]:
        return self.raw.get("nodes", {}) or {}

    @property
    def sources(self) -> dict[str, Any]:
        return self.raw.get("sources", {}) or {}

    @property
    def exposures(self) -> dict[str, Any]:
        return self.raw.get("exposures", {}) or {}

    @property
    def child_map(self) -> dict[str, list[str]]:
        return self.raw.get("child_map", {}) or {}

    @property
    def parent_map(self) -> dict[str, list[str]]:
        return self.raw.get("parent_map", {}) or {}


def read_manifest(path: str | Path) -> Manifest:
    """Load and parse target/manifest.json. Raises ArtifactError on structural failure."""
    p = Path(path)
    if not p.is_file():
        raise ArtifactError(f"manifest not found: {p}")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ArtifactError(f"manifest at {p} is not valid JSON: {e}") from e
    if not isinstance(raw, dict):
        raise ArtifactError(f"manifest at {p} is not a JSON object")

    md = raw.get("metadata") or {}
    schema_url = md.get("dbt_schema_version", "")
    schema_short = _short_schema(schema_url)
    if schema_short and schema_short not in KNOWN_MANIFEST_SCHEMAS:
        logger.info(
            "manifest schema %s is newer than known list (%s); proceeding with defensive reads",
            schema_short, ",".join(KNOWN_MANIFEST_SCHEMAS),
        )

    return Manifest(
        metadata=ManifestMetadata(
            dbt_version=md.get("dbt_version", "unknown"),
            dbt_schema_version=schema_url or "unknown",
            project_name=md.get("project_name", "unknown"),
            adapter_type=md.get("adapter_type"),
            generated_at=md.get("generated_at"),
        ),
        raw=raw,
    )


def read_catalog(path: str | Path) -> dict[str, Any] | None:
    """Load target/catalog.json. Returns None if missing — catalog is optional."""
    p = Path(path)
    if not p.is_file():
        logger.debug("catalog not found at %s — proceeding without column types", p)
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.warning("catalog at %s is not valid JSON: %s — ignoring", p, e)
        return None


def read_run_results(path: str | Path) -> dict[str, Any] | None:
    """Load target/run_results.json. Returns None if missing — file is optional."""
    p = Path(path)
    if not p.is_file():
        logger.debug("run_results not found at %s — proceeding without execution stats", p)
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.warning("run_results at %s is not valid JSON: %s — ignoring", p, e)
        return None


def _short_schema(url: str) -> str | None:
    """Pull the `vN` token out of a manifest schema URL.

    Example: https://schemas.getdbt.com/dbt/manifest/v12.json -> v12
    Strips trailing slashes, query strings, and fragments before matching.
    """
    if not url:
        return None
    # Strip trailing slash, ?query, #fragment.
    head = url.rstrip("/").split("?", 1)[0].split("#", 1)[0]
    last = head.split("/")[-1]
    if last.startswith("v") and last.endswith(".json"):
        return last[: -len(".json")]
    return None
