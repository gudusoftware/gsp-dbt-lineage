from gsp_dbt_lineage.confidence import annotate_dynamic_sql, compute_node_confidence


def test_high_when_all_resolved():
    cols = [
        {"name": "a", "upstream": [{"table": "t", "column": "a"}]},
        {"name": "b", "upstream": [{"table": "t", "column": "b"}]},
    ]
    assert compute_node_confidence(cols) == "high"


def test_medium_when_some_resolved():
    cols = [
        {"name": "a", "upstream": [{"table": "t", "column": "a"}]},
        {"name": "b", "upstream": []},
    ]
    assert compute_node_confidence(cols) == "medium"


def test_low_when_none_resolved():
    cols = [
        {"name": "a", "upstream": []},
        {"name": "b", "upstream": []},
    ]
    assert compute_node_confidence(cols) == "low"


def test_empty_columns_low():
    assert compute_node_confidence([]) == "low"


def test_dynamic_sql_caps_confidence_low():
    node = {"status": "parsed", "confidence": "high", "unresolved": [], "columns": []}
    out = annotate_dynamic_sql(node, "SELECT 1; EXECUTE IMMEDIATE @sql;")
    assert out["confidence"] == "low"
    assert out["status"] == "partial"
    assert any(u["reason"] == "dynamic_sql" for u in out["unresolved"])


def test_no_dynamic_sql_marker_passes_through():
    node = {"status": "parsed", "confidence": "high", "unresolved": [], "columns": []}
    out = annotate_dynamic_sql(node, "SELECT 1 FROM x")
    assert out["confidence"] == "high"
    assert out["status"] == "parsed"
    assert out["unresolved"] == []
