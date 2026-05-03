# E04b — Real user-reported BigQuery procedural SQL (datahub#11654)

- **Source issue**: [datahub-project/datahub#11654](https://github.com/datahub-project/datahub/issues/11654) — "BigQuery Ingestion Fails to Create Lineage Due to SQL Parsing Errors in sqlglot"
- **Reporter**: @Nirvikalpa108 (later confirmed by @vejeta as the same team)
- **Reported SQL**: see `input.sql` (verbatim from issue body, "obfuscated anything specific to our business")
- **sqlglot version tested**: 30.6.0 → `ParseError` on the nested `IF (SELECT COUNT(1) FROM temp_table_delta) > 0 THEN` block; preceding `CALL` and outer `IF` fall back to `Command`
- **GSP version tested**: local JAR `gsqlparser-4.1.0.15-shaded.jar` (cloud `exportFullLineageAsJson` returns 500 on this SQL — see open GSP cloud-side bug)
- **Cached GSP response**: `materials/dbt-lineage-evidence/poc-responses/E04b_response.json`
- **Companion blog walkthrough**: [Why your DataHub BigQuery lineage silently breaks on procedural SQL — and the fix](https://www.dpriver.com/blog/2026/04/why-your-datahub-bigquery-lineage-silently-breaks-on-procedural-sql-and-how-to-f/?utm_source=datahub&utm_medium=oss&utm_campaign=issue-11654&utm_content=blog-walkthrough)
- **Companion landing page**: [DataHub BigQuery lineage sidecar — install + CLI](https://www.sqlparser.com/datahub/bigquery-lineage/?utm_source=datahub&utm_medium=oss&utm_campaign=issue-11654&utm_content=landing-page)

## Verified claim

| Metric | sqlglot 30.6.0 | GSP/SQLFlow 4.1.0.15 |
|---|---|---|
| Parser status | `ParseError` (hard fail) | `parsed` |
| Real upstream tables | 0 | 2 (`project.dataset.view_name`, `temp_table_delta`) |
| Write targets | 0 | 2 (`temp_table` ← view_name; `final_output` ← temp_table_delta) |
| Column edges | 0 | 11 (6 + 5, see `expected_lineage.json[evidence.procedural]`) |

## Known limitation surfaced

The `CALL internal_project.get_partitions(...)` body is opaque to GSP — only
the call site is observed; lineage from the called procedure into the
`partitions` STRUCT it populates is not traced. This is documented in
`docs/known-limitations.md` and does not affect the headline write-target
edges, which are recovered correctly.
