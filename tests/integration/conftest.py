"""Integration-test fixtures shared across the per-fixture E* tests.

Active fixtures are materialized into fixtures/evidence/ from the Phase 0.4
PoC cache. We do NOT call the live api.gudusoft.com from tests — that would
burn the anonymous quota in CI. Instead, the per-fixture test reads the
cached GSP response and runs it through our lineage_mapper, then validates
the whole chain (mapper → schema validation → semantic resolution →
differential vs dbt stock).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_ROOT = REPO_ROOT / "fixtures/evidence"
EVIDENCE_DIR = Path("/home/ubuntu/github/gudu-agent-team/materials/dbt-lineage-evidence")


def _load_cached_response(fid: str) -> dict:
    p = EVIDENCE_DIR / "poc-responses" / f"{fid}_response.json"
    wrapped = json.loads(p.read_text(encoding="utf-8"))
    return wrapped.get("body") if isinstance(wrapped, dict) and "body" in wrapped else wrapped


@pytest.fixture
def fixture_loader():
    """Returns a callable that loads (sql, dialect, expected_doc, gsp_response) for a fixture."""

    def _load(fixture_dir_name: str):
        d = FIXTURES_ROOT / fixture_dir_name
        meta = yaml.safe_load((d / "metadata.yml").read_text(encoding="utf-8"))
        return {
            "id": meta["id"],
            "label": meta["label"],
            "dialect": meta["dbvendor"],
            "sql": (d / "input.sql").read_text(encoding="utf-8"),
            "expected": json.loads((d / "expected_lineage.json").read_text(encoding="utf-8")),
            "stock": json.loads((d / "dbt_stock_lineage.json").read_text(encoding="utf-8")),
            "expected_upstream_tables": meta.get("expected_upstream_tables") or [],
            "expected_downstream_tables": meta.get("expected_downstream_tables") or [],
            "gsp_response": _load_cached_response(meta["id"]),
        }

    return _load
