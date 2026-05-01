"""Phase 4 task 4.1 — 11 sqlglot regression canaries.

Each test exercises a sqlglot construct that was an `active` failure at some
point in the past (cited in DataHub / OpenMetadata issue threads or sqlglot
bug reports). All 11 are `regression` (sqlglot has fixed them) as of
sqlglot 30.6.0, the version the v1 plan was scoped against.

If any test below fails, sqlglot has regressed and a row needs to flip back to
`active` in materials/dbt-lineage-evidence/index.yml — see _regression/README.md.

We test sqlglot directly here (no GSP, no manifest). The intent is "does
sqlglot still handle this," not "does our package handle this."
"""

from __future__ import annotations

import pytest

sqlglot = pytest.importorskip("sqlglot")
from sqlglot.errors import OptimizeError, ParseError  # noqa: E402
from sqlglot.lineage import lineage  # noqa: E402
from sqlglot.optimizer.qualify import qualify  # noqa: E402
from sqlglot.optimizer.qualify_columns import qualify_columns  # noqa: E402
from sqlglot.schema import ensure_schema  # noqa: E402


def _qc(sql: str, dialect: str, schema: dict | None = None, expand_stars: bool = True):
    ast = sqlglot.parse_one(sql, dialect=dialect)
    s = ensure_schema(schema, dialect=dialect)
    return qualify_columns(ast, s, expand_alias_refs=True, expand_stars=expand_stars, infer_schema=None)


def _q(sql: str, dialect: str, schema: dict | None = None):
    ast = sqlglot.parse_one(sql, dialect=dialect)
    return qualify(ast, schema=schema, dialect=dialect)


def test_E07_bigquery_nested_star():
    """sqlglot#3484 — nested star (foo.bar.*) in BigQuery."""
    _qc("SELECT foo.bar.* FROM foo", "bigquery")


def test_E08_bigquery_struct_field_lineage():
    """sqlglot#6258 — STRUCT lineage granularity."""
    sql = """
    WITH src AS (
      SELECT STRUCT(id AS uid, name AS uname) AS user_info FROM raw_users
    )
    SELECT user_info.uname AS resolved_name FROM src
    """
    schema = {"raw_users": {"id": "INT64", "name": "STRING"}}
    ln = lineage("resolved_name", sql, schema=schema, dialect="bigquery")
    leaves = []

    def walk(n):
        if not n.downstream:
            leaves.append(str(n.source))
        for d in n.downstream:
            walk(d)

    walk(ln)
    assert any("raw_users" in s for s in leaves), leaves


def test_E09_bigquery_unnest_with_offset():
    """sqlglot#7447 — array[offset] where offset is bound by UNNEST WITH OFFSET."""
    sql = """
    SELECT arr[offset] AS val
    FROM t, UNNEST(t.arr_col) AS arr WITH OFFSET AS offset
    """
    sqlglot.parse_one(sql, dialect="bigquery")


def test_E11_snowflake_lateral_flatten_lowercase_value():
    """sqlglot#3006 — Snowflake LATERAL FLATTEN with lowercase 'value' column."""
    sql = """
    SELECT d.ORDER_ID, f.value
    FROM DISCOUNTS AS d, LATERAL FLATTEN(input => d.DISCOUNTS_ARRAY) AS f
    """
    schema = {"DISCOUNTS": {"ORDER_ID": "NUMBER", "DISCOUNTS_ARRAY": "ARRAY"}}
    _q(sql, "snowflake", schema=schema)


def test_E12_snowflake_select_star_pivot_cte():
    """sqlglot#4137 — Snowflake SELECT * + PIVOT inside a CTE."""
    sql = """
    WITH t AS (SELECT a, b, val FROM raw)
    SELECT *
    FROM t
    PIVOT(SUM(val) FOR b IN ('x', 'y')) AS p
    """
    schema = {"raw": {"a": "STRING", "b": "STRING", "val": "NUMBER"}}
    _q(sql, "snowflake", schema=schema)


def test_E13_snowflake_group_by_qualify():
    """sqlglot#7043 — Snowflake GROUP BY combined with QUALIFY."""
    sql = """
    SELECT a, COUNT(*) AS c
    FROM tbl
    GROUP BY a
    QUALIFY ROW_NUMBER() OVER (ORDER BY a) = 1
    """
    schema = {"tbl": {"a": "STRING", "b": "STRING"}}
    _q(sql, "snowflake", schema=schema)


def test_E14_databricks_struct_values_alias():
    """sqlglot#6879 — Databricks named_struct alias 'values' (reserved kw)."""
    sqlglot.parse_one("SELECT named_struct('values', a) AS s FROM t", dialect="databricks")


def test_E15_databricks_recursive_cte_preserved():
    """sqlglot#7213 — RECURSIVE keyword preserved on output for Databricks."""
    sql = "WITH RECURSIVE t(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM t WHERE n<10) SELECT * FROM t"
    rendered = sqlglot.parse_one(sql, dialect="databricks").sql(dialect="databricks")
    assert "RECURSIVE" in rendered.upper()


def test_E24_tsql_merge_in_parens():
    """sqlglot#4884 — T-SQL MERGE wrapped in parens (CTE-style)."""
    sql = """
    MERGE INTO target AS t
    USING (SELECT id, val FROM src) AS s
    ON t.id = s.id
    WHEN MATCHED THEN UPDATE SET t.val = s.val
    WHEN NOT MATCHED THEN INSERT (id, val) VALUES (s.id, s.val);
    """
    sqlglot.parse_one(sql, dialect="tsql")


def test_E25_tsql_option_maxrecursion_on_update():
    """sqlglot#6033 — T-SQL UPDATE ... OPTION (MAXRECURSION 0)."""
    sql = "UPDATE t SET c = 1 OPTION (MAXRECURSION 0)"
    sqlglot.parse_one(sql, dialect="tsql")


def test_E26_oracle_merge_conditionals():
    """sqlglot#6529 — Oracle MERGE with conditional WHEN ... AND clauses."""
    sql = """
    MERGE INTO target t
    USING src s ON (t.id = s.id)
    WHEN MATCHED THEN UPDATE SET t.v = s.v WHERE s.flag = 1
    WHEN NOT MATCHED THEN INSERT (id, v) VALUES (s.id, s.v) WHERE s.flag = 0
    """
    sqlglot.parse_one(sql, dialect="oracle")
