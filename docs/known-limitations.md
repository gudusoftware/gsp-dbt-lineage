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

For procedural BigQuery / T-SQL scripts that write to multiple TEMP TABLE / real-table targets in a single compiled statement (e.g., the `datahub#11654` pattern — `CREATE OR REPLACE TEMP TABLE temp_table AS …` followed by `CREATE OR REPLACE TEMP TABLE final_output AS …` inside one procedural script), same-named output columns also collapse in the flat `columns` list. The per-target attribution is preserved in `node.evidence.procedural.write_targets`, which is the authoritative receipt — emitters and reviewers should consult that block when the procedural pattern is in play. See fixture `E04b_bigquery_procedural_real_datahub_11654` for the worked example.

## 7. Opaque CALL / stored-procedure bodies

When a BigQuery `CALL <db.proc>(args)` or T-SQL `EXEC <proc>` is invoked but
the called procedure's body is not present in the same compilation unit,
GSP records the call site but does not trace lineage from the procedure
into any output variables it populates. In `datahub#11654` the script's
`CALL internal_project.get_partitions(..., partitions)` populates the
`partitions` STRUCT, which is then read in a downstream `IF ARRAY_LENGTH(partitions.dates) > 0` predicate — the upstream of `partitions` is
opaque to lineage. The headline write-target edges (`temp_table` ←
`view_name`, `final_output` ← `temp_table_delta`) are still recovered
correctly. Workaround: include the called procedure's body in the same
parse if available.

## 8. Local-JAR JVM cold start

`--backend local_jar` shells out to a Java subprocess per call. Cold start is ~0.5–1s. For projects above ~100 nodes, prefer `--backend self_hosted` (one container, persistent JVM).

## 9. Two-part install (only if using the dbt-side macros)

The runtime CLI is a single `pip install gsp-dbt-lineage`. The dbt-side package (`gudusoftware/gsp_dbt_lineage` via `packages.yml` + `dbt deps`) is **optional** — install only if you want `gudu_lineage` dbt vars exposed to the manifest. Most users skip the dbt package entirely.

ADR-007 captures the architectural reason the runtime cannot live inside macros.
