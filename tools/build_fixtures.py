#!/usr/bin/env python3
"""Materialize fixtures/evidence/E*/ from the Phase 0.4 PoC dossier.

Reads:
  - The FIXTURES list from materials/dbt-lineage-evidence/poc_run.py (companion repo)
  - Cached GSP responses under materials/dbt-lineage-evidence/poc-responses/
  - The sqlglot-30.6.0 baseline from materials/dbt-lineage-evidence/results.json

Writes one directory per active fixture under fixtures/evidence/<id>_<slug>/:
  - input.sql
  - dialect.txt
  - expected_lineage.json (built from the cached GSP response by lineage_mapper)
  - dbt_stock_lineage.json (empty for active rows; for `partial` rows we record
    what dbt's stock CLL produces — empty by default)
  - current_oss_behavior.json (the sqlglot Phase 0.1 result)
  - metadata.yml (label, source issue, contributor)
  - LINKS.md

Idempotent: re-running overwrites the fixtures.

Usage:
  python tools/build_fixtures.py --evidence-dir /home/ubuntu/github/gudu-agent-team/materials/dbt-lineage-evidence
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_ROOT = REPO_ROOT / "fixtures/evidence"


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:60]


def load_fixtures(poc_path: Path) -> list[dict]:
    spec = importlib.util.spec_from_file_location("poc_run", poc_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.FIXTURES


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", required=True,
                        help="Path to materials/dbt-lineage-evidence/ in companion repo")
    args = parser.parse_args()

    evdir = Path(args.evidence_dir).resolve()
    fixtures = load_fixtures(evdir / "poc_run.py")

    # Make our internal mapper importable at build time.
    sys.path.insert(0, str(REPO_ROOT / "python"))
    from gsp_dbt_lineage.lineage_mapper import map_gsp_to_node  # noqa: E402

    # Phase 0.1 sqlglot baseline.
    sqlglot_results = json.loads((evdir / "results.json").read_text(encoding="utf-8"))
    baseline_by_id = {r["id"]: r for r in sqlglot_results.get("rows", [])}

    written = 0
    skipped = 0
    for fx in fixtures:
        fid = fx["id"]
        # Skip E06 (GSP loses) — the runbook treats this as known-limitation, not a fixture.
        if fid == "E06":
            skipped += 1
            continue

        slug = f"{fid}_{slugify(fx['description'])}"
        out = FIXTURES_ROOT / slug
        out.mkdir(parents=True, exist_ok=True)

        # 1. SQL
        (out / "input.sql").write_text(fx["sql"].strip() + "\n", encoding="utf-8")

        # 2. dialect
        (out / "dialect.txt").write_text(fx["dbvendor"] + "\n", encoding="utf-8")

        # 3. cached GSP response → expected_lineage.json
        resp_path = evdir / "poc-responses" / f"{fid}_response.json"
        if not resp_path.is_file():
            print(f"[skip] {fid}: no cached response at {resp_path}")
            skipped += 1
            continue
        wrapped = json.loads(resp_path.read_text(encoding="utf-8"))
        # The PoC stored {http_status, body}; unwrap to the body.
        response = wrapped.get("body") if isinstance(wrapped, dict) and "body" in wrapped else wrapped
        node = map_gsp_to_node(response, node_id=f"fixture.{fid}", dialect=fx["dbvendor"])
        expected_doc = {
            "schema_version": "0.2.x",
            "generator": "build_fixtures.py",
            "manifest_metadata": {
                "dbt_version": "fixture",
                "project_name": "fixture",
                "selected_count": 1,
                "eligible_count": 1,
                "adapter_type": fx["dialect"],
            },
            "backend": {"mode": "fixture", "parser_version": "phase-0.4-cache", "cli_version": "0.0.1"},
            "stats": {
                "parsed": 1 if node["status"] == "parsed" else 0,
                "partial": 1 if node["status"] == "partial" else 0,
                "unsupported": 1 if node["status"] == "unsupported" else 0,
                "failed": 0,
                "skipped": 0,
                "total_columns": len(node["columns"]),
                "resolved_columns": sum(1 for c in node["columns"] if c["upstream"]),
                "coverage": (
                    round(sum(1 for c in node["columns"] if c["upstream"]) / max(1, len(node["columns"])), 4)
                    if node["columns"] else 0.0
                ),
            },
            "nodes": [node],
        }
        (out / "expected_lineage.json").write_text(
            json.dumps(expected_doc, indent=2, sort_keys=True), encoding="utf-8"
        )

        # 4. dbt_stock_lineage.json — Phase 0.1 documents that sqlglot returns empty/wrong
        # for every active fixture. Encode that explicitly so tests can assert "we beat dbt CLL".
        stock_doc = {
            "schema_version": "0.2.x",
            "generator": "dbt-stock-cll-baseline (phase-0.1)",
            "nodes": [{
                "node_id": f"fixture.{fid}",
                "status": "unsupported",
                "confidence": "low",
                "dialect": fx["dbvendor"],
                "upstream_tables": [],
                "downstream": [],
                "columns": [],
                "unresolved": [{"reason": "sqlglot_baseline", "phase01_result": baseline_by_id.get(fid, {}).get("result")}],
                "warnings": [],
            }],
        }
        (out / "dbt_stock_lineage.json").write_text(
            json.dumps(stock_doc, indent=2, sort_keys=True), encoding="utf-8"
        )

        # 5. current_oss_behavior.json — sqlglot Phase 0.1 row
        current = baseline_by_id.get(fid) or {}
        (out / "current_oss_behavior.json").write_text(
            json.dumps(current, indent=2, sort_keys=True), encoding="utf-8"
        )

        # 6. metadata.yml
        meta = {
            "id": fid,
            "label": fx.get("label", "active"),
            "dialect": fx["dialect"],
            "dbvendor": fx["dbvendor"],
            "description": fx["description"],
            "sqlglot_phase01_result": fx.get("sqlglot_result"),
            "expected_upstream_tables": fx.get("expected_upstream_tables", []),
            "expected_downstream_tables": fx.get("expected_downstream_tables", []),
            "source_evidence_index": "materials/dbt-lineage-evidence/index.yml",
        }
        (out / "metadata.yml").write_text(yaml.safe_dump(meta, sort_keys=False), encoding="utf-8")

        # 7. LINKS.md
        (out / "LINKS.md").write_text(
            f"# {fid} — {fx['description']}\n\n"
            f"- Phase 0.1 sqlglot result: `{fx.get('sqlglot_result')}`\n"
            f"- Phase 0.4 PoC: `materials/dbt-lineage-evidence/poc-dossier.md`\n"
            f"- Cached GSP response: `materials/dbt-lineage-evidence/poc-responses/{fid}_response.json`\n",
            encoding="utf-8",
        )

        written += 1

    print(f"wrote {written} fixtures, skipped {skipped} (incl E06 known-limitation)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
