from pathlib import Path

from gsp_dbt_lineage.compiled_sql import get_compiled_sql, is_eligible_for_lineage


def test_inline_compiled_code():
    node = {"compiled_code": "SELECT * FROM x"}
    assert get_compiled_sql(node) == "SELECT * FROM x"


def test_legacy_compiled_sql_field():
    node = {"compiled_sql": "SELECT 2"}
    assert get_compiled_sql(node) == "SELECT 2"


def test_compiled_path_fallback(tmp_path):
    target = tmp_path / "target"
    rel = "compiled/demo/models/stg.sql"
    p = target / rel
    p.parent.mkdir(parents=True)
    p.write_text("SELECT 99", encoding="utf-8")
    node = {"compiled_path": rel}
    assert get_compiled_sql(node, target) == "SELECT 99"


def test_no_sql_returns_none():
    assert get_compiled_sql({}) is None


def test_eligibility():
    assert is_eligible_for_lineage({"resource_type": "model"}) == (True, None)
    ok, reason = is_eligible_for_lineage({"resource_type": "test"})
    assert not ok and "test" in reason
    ok, reason = is_eligible_for_lineage({"resource_type": "seed"})
    assert not ok and "seed" in reason
    ok, reason = is_eligible_for_lineage({})
    assert not ok and "missing" in reason
