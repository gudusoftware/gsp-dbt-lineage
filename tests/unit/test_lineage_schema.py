import pytest

from gsp_dbt_lineage.lineage_schema import SCHEMA_VERSION, SchemaError, validate_lineage


def _minimal_doc() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generator": "test",
        "manifest_metadata": {
            "dbt_version": "1.7.4",
            "project_name": "demo",
            "selected_count": 0,
            "eligible_count": 0,
        },
        "backend": {"mode": "anonymous"},
        "stats": {},
        "nodes": [],
    }


def test_minimal_valid():
    validate_lineage(_minimal_doc())


def test_node_with_columns():
    doc = _minimal_doc()
    doc["nodes"] = [{
        "node_id": "model.x.a",
        "status": "parsed",
        "confidence": "high",
        "dialect": "dbvbigquery",
        "upstream_tables": ["src.t"],
        "downstream": [],
        "columns": [{
            "name": "id",
            "upstream": [{"table": "src.t", "column": "id"}],
            "transform": "direct",
            "confidence": "high",
        }],
        "unresolved": [],
        "warnings": [],
    }]
    validate_lineage(doc)


def test_invalid_status_rejected():
    doc = _minimal_doc()
    doc["nodes"] = [{"node_id": "x", "status": "synthesized"}]
    with pytest.raises(SchemaError):
        validate_lineage(doc)


def test_invalid_confidence_rejected():
    doc = _minimal_doc()
    doc["nodes"] = [{"node_id": "x", "status": "parsed", "confidence": "very-high"}]
    with pytest.raises(SchemaError):
        validate_lineage(doc)


def test_missing_required_field_rejected():
    doc = _minimal_doc()
    del doc["nodes"]
    with pytest.raises(SchemaError):
        validate_lineage(doc)


def test_extra_fields_allowed():
    doc = _minimal_doc()
    doc["future_added_field"] = {"x": 1}
    validate_lineage(doc)
