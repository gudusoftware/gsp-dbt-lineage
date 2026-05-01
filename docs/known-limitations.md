# Known limitations (binding for v1)

## 1. BigQuery UDF return STRUCT

```sql
SELECT `proj.ds.func`(data).*
FROM `proj.ds.tbl`
```

Both sqlglot and GSP fail to parse this construct (verified Phase 0.4 PoC). GSP returns `SyntaxError near *`.

**User-facing message:** "BigQuery user-defined function return STRUCTs (the `func(args).*` star expansion) are not currently supported."

**Workaround:** flatten via subquery first.

This is tracked internally; the next quarterly re-survey will promote E06 to active if GSP grammar is fixed.

## 2. Snowflake / Databricks dialect-fix marketing

We do NOT advertise dialect coverage on Snowflake or Databricks for these constructs because sqlglot 30.6.0 now handles them:

- LATERAL FLATTEN, QUALIFY, PIVOT/CTE, recursive CTE, struct alias.
- T-SQL MERGE-in-parens, OPTION-MAXRECURSION.

The package still **works** on these dialects — but the parser-superiority story we cannot honestly tell. They live in `fixtures/evidence/_regression/` as canaries for a sqlglot regression.

## 3. Dynamic SQL

`EXECUTE IMMEDIATE`, `EXEC sp_executesql @sql`, and similar dynamic constructs cannot be statically resolved. The package emits `confidence: low` and an `unresolved` array entry per the C10 constraint. We never fabricate edges.

## 4. dbt Cloud Explorer

No third-party plug-in surface for dbt Cloud Explorer exists at v1. Users running dbt Cloud must run the CLI in their CI environment after artifact download from the dbt Cloud API. See `docs/ci-integration.md`.

## 5. Manifest mutation

We do NOT mutate `manifest.json`. Output is sidecar only (`target/gudu/column_lineage.json`). Reasoning: dbt-core may change manifest schema between minors; sidecar pattern is forward-compatible. Revisit at v2.

## 6. Multiple result-set projections collapsed by name

In the rare case where a single dbt model produces multiple top-level result-sets that each project a column with the same name (e.g., a UNION of two SELECTs both projecting `id`), the current mapper merges their upstream lineage. For most dbt SQL this is the right answer; for unusual patterns the merged lineage may overstate provenance. Tracked for Phase 3+.

## 7. Local-JAR JVM cold start

`--backend local_jar` shells out to a Java subprocess per call. Cold start is ~0.5–1s. For projects above ~100 nodes, prefer `--backend self_hosted` (one container, persistent JVM).

## 8. Two-part install

Currently requires `pip install gsp-dbt-lineage` AND `dbt deps` for the package macros. Phase 0.5 user research validated this; if revisited, ADR-007 captures the architectural reasoning for keeping the runtime in Python.
