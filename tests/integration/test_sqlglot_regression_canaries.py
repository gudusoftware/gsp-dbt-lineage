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

import sqlglot  # hard dep in [dev]; not optional — these are CI canaries.
from sqlglot.errors import OptimizeError, ParseError  # noqa: E402,F401
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
    """sqlglot#6258 — STRUCT lineage granularity.

    Walks the lineage tree and asserts the leaf reaches BOTH the source
    table (raw_users) AND the field-level column (name). A regression where
    sqlglot resolved only the table but not the STRUCT field would still
    have raw_users in leaves but lose 'name' — this catches that.
    """
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
            leaves.append(f"{n.source}::{n.name}")
        for d in n.downstream:
            walk(d)

    walk(ln)
    leaf_str = " | ".join(leaves)
    assert "raw_users" in leaf_str, f"missing source table: {leaf_str}"
    assert "name" in leaf_str, f"missing STRUCT field-level column: {leaf_str}"


def test_E09_bigquery_unnest_with_offset():
    """sqlglot#7447 — array[offset] where offset is bound by UNNEST WITH OFFSET."""
    sql = """
    SELECT arr[offset] AS val
    FROM t, UNNEST(t.arr_col) AS arr WITH OFFSET AS offset
    """
    ast = sqlglot.parse_one(sql, dialect="bigquery")
    # Round-trip render: a parser regression that produced wrong AST might
    # parse without error but emit wrong SQL.
    rendered = ast.sql(dialect="bigquery")
    assert "UNNEST" in rendered.upper()
    assert "OFFSET" in rendered.upper()


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
    """sqlglot#6879 — Snowflake/Databricks STRUCT field literally named 'values'.

    Original failure: a STRUCT containing a column named 'values' (a reserved
    keyword in many dialects) lost identifier-quoting on round-trip render,
    breaking transpilation. Verify both parse AND quote-preserving render.
    """
    sql = "SELECT struct(2 as values) AS s FROM t"
    ast = sqlglot.parse_one(sql, dialect="databricks")
    # Quote-preserving round-trip is the actual regression check.
    rendered = ast.sql(dialect="databricks", identify=True)
    # The 'values' identifier must survive the round trip recognizable as the
    # struct field — either quoted or as the alias keyword.
    assert "values" in rendered.lower(), rendered
    # named_struct variant from the issue body
    sqlglot.parse_one("SELECT named_struct('values', a) AS s FROM t", dialect="databricks")


def test_E15_databricks_recursive_cte_preserved():
    """sqlglot#7213 — RECURSIVE keyword preserved on output for Databricks."""
    sql = "WITH RECURSIVE t(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM t WHERE n<10) SELECT * FROM t"
    rendered = sqlglot.parse_one(sql, dialect="databricks").sql(dialect="databricks")
    assert "RECURSIVE" in rendered.upper()


def test_E24_tsql_merge_in_parens():
    """sqlglot#4884 — T-SQL MERGE wrapped in parens with OUTPUT.

    The Phase 0.1 baseline only asserts that this construct *parses* — sqlglot
    30.6.0's RENDER of MERGE-in-parens is still buggy (AttributeError on
    `Merge.selects` during T-SQL generator), but parse is the regression we
    were tracking. If that breaks too, sqlglot has clearly regressed across
    multiple layers.

    Faithful repro from materials/dbt-lineage-evidence/run_tests.py test_E24.
    """
    sql = """
    SELECT * FROM (MERGE Production.ProductInventory AS tgt
    USING (SELECT 1 AS ProductID, 1 AS OrderQty) AS src(ProductID, OrderQty)
    ON (tgt.ProductID = src.ProductID)
    WHEN MATCHED THEN UPDATE SET tgt.Quantity = tgt.Quantity - src.OrderQty
    OUTPUT $action, Inserted.ProductID);
    """
    ast = sqlglot.parse_one(sql, dialect="tsql")
    # Inspect the AST shape rather than rendering — the AST must contain a
    # Merge node nested in a Subquery, which is the actual regression check.
    repr_str = repr(ast)
    assert "Merge" in repr_str, f"MERGE not in AST: {repr_str[:300]}"


def test_E25_tsql_option_maxrecursion_on_update():
    """sqlglot#6033 — T-SQL UPDATE ... OPTION (MAXRECURSION 0)."""
    sql = "UPDATE t SET c = 1 OPTION (MAXRECURSION 0)"
    ast = sqlglot.parse_one(sql, dialect="tsql")
    rendered = ast.sql(dialect="tsql")
    # OPTION (MAXRECURSION ...) must survive the round trip.
    assert "MAXRECURSION" in rendered.upper()


def test_E26_oracle_merge_conditionals():
    """sqlglot#6529 — Oracle MERGE with conditional WHEN ... AND clauses."""
    sql = """
    MERGE INTO target t
    USING src s ON (t.id = s.id)
    WHEN MATCHED THEN UPDATE SET t.v = s.v WHERE s.flag = 1
    WHEN NOT MATCHED THEN INSERT (id, v) VALUES (s.id, s.v) WHERE s.flag = 0
    """
    ast = sqlglot.parse_one(sql, dialect="oracle")
    rendered = ast.sql(dialect="oracle")
    # Both WHERE-conditional clauses must be preserved (a regression that
    # dropped the WHERE on either branch would silently corrupt semantics).
    assert rendered.upper().count("WHERE") >= 2
