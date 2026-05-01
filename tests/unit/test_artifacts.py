import json
from pathlib import Path

import pytest

from gsp_dbt_lineage.artifacts import (
    ArtifactError,
    read_catalog,
    read_manifest,
    read_run_results,
)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_manifest(adapter: str = "bigquery", schema: str = "v12") -> dict:
    return {
        "metadata": {
            "dbt_version": "1.7.4",
            "dbt_schema_version": f"https://schemas.getdbt.com/dbt/manifest/{schema}.json",
            "project_name": "demo",
            "adapter_type": adapter,
            "generated_at": "2026-05-01T00:00:00Z",
        },
        "nodes": {
            "model.demo.stg_orders": {
                "name": "stg_orders",
                "resource_type": "model",
                "fqn": ["demo", "staging", "stg_orders"],
                "compiled_code": "SELECT 1",
            },
        },
        "sources": {},
        "child_map": {"model.demo.stg_orders": []},
        "parent_map": {"model.demo.stg_orders": []},
    }


def test_read_manifest_returns_metadata(tmp_path):
    p = tmp_path / "manifest.json"
    _write_json(p, _make_manifest())
    m = read_manifest(p)
    assert m.metadata.dbt_version == "1.7.4"
    assert m.metadata.adapter_type == "bigquery"
    assert "model.demo.stg_orders" in m.nodes


def test_read_manifest_missing_raises(tmp_path):
    with pytest.raises(ArtifactError):
        read_manifest(tmp_path / "nope.json")


def test_read_manifest_invalid_json_raises(tmp_path):
    p = tmp_path / "manifest.json"
    p.write_text("not json", encoding="utf-8")
    with pytest.raises(ArtifactError):
        read_manifest(p)


def test_read_manifest_unknown_schema_logs_but_succeeds(tmp_path, caplog):
    p = tmp_path / "manifest.json"
    _write_json(p, _make_manifest(schema="v999"))
    m = read_manifest(p)
    assert m.metadata.dbt_version == "1.7.4"


def test_read_catalog_missing_returns_none(tmp_path):
    assert read_catalog(tmp_path / "missing.json") is None


def test_read_run_results_missing_returns_none(tmp_path):
    assert read_run_results(tmp_path / "missing.json") is None


def test_manifest_handles_dbt_1_5_through_1_8(tmp_path):
    for schema in ("v9", "v10", "v11", "v12"):
        p = tmp_path / f"m_{schema}.json"
        _write_json(p, _make_manifest(schema=schema))
        m = read_manifest(p)
        assert m.metadata.dbt_schema_version.endswith(f"{schema}.json")
