# E16b — Real user-reported MSSQL stored procedure (OpenMetadata#25299)

- **Source issue**: [open-metadata/OpenMetadata#25299](https://github.com/open-metadata/OpenMetadata/issues/25299) — "Stored Procedure lineage is not supported for MS SQL connector"
- **Reporter**: @antonsyagailo-obs (confirmed by @RickLeite on the related #17586)
- **Reported SQL**: see `input.sql` (verbatim from the issue's "To Reproduce" block, including the full database/schema/table DDL setup, the `CREATE PROCEDURE schName.procName AS BEGIN … END` body with the `#tempTable` 3-hop chain, and the 13 `EXECUTE schName.procName` calls the reporter pasted)
- **OpenMetadata version impact**: reporter observed empty lineage on 1.10.0, 1.10.4, and 1.11.2; related #17586 marked CLOSED by the `LIKE '%create%procedure%'` filter removal in PR #14586, but the symptom persists because the parser chain bails on the procedural wrapper after the filter is gone
- **Parser chain tested in the issue**: `sqlglot` → `sqlfluff` → `sqlparse` (collate-sqllineage default); all three return 0 column edges on this SQL
- **GSP version tested**: local JAR `gsqlparser-4.1.0.15-shaded.jar` (cloud `exportFullLineageAsJson` not retried for this fixture; local JAR is sufficient for the cached PoC pipeline)
- **Cached GSP response**: `materials/dbt-lineage-evidence/poc-responses/E16b_response.json`
- **Companion blog walkthrough**: [Why MSSQL stored-procedure lineage is silently empty in OpenMetadata (and the fix)](https://www.dpriver.com/blog/2026/04/openmetadata-mssql-stored-procedures-why-your-lineage-is-silently-empty-and-how/?utm_source=openmetadata&utm_medium=oss&utm_campaign=issue-25299&utm_content=blog-walkthrough)
- **Companion landing page**: [OpenMetadata MSSQL sidecar landing page](https://www.sqlparser.com/openmetadata/?utm_source=openmetadata&utm_medium=oss&utm_campaign=issue-25299&utm_content=landing-page)

## Verified claim

| Metric | OpenMetadata CLL chain (sqlglot 30.6.0 → sqlfluff → sqlparse) | GSP/SQLFlow 4.1.0.15 |
|---|---|---|
| Parser status | `unsupported` (procedural wrapper not entered) | `parsed` |
| Real upstream tables | 0 | 3 (`dbName.schName.sourceTable`, `dbName.dbo.#tempTable`, `dbName.schName.targetTable`) |
| Write targets | 0 | 2 (`#tempTable` ← `sourceTable`; `targetTable` ← `#tempTable`) |
| Column edges | 0 | 2 (`columnName` → `columnName` on each hop) |
| Temp-table subType marked | n/a | yes (`subType: temp_table` on `#tempTable`) |

## Parallel to E04b

This fixture stands to MSSQL stored procedures as `E04b_bigquery_procedural_real_datahub_11654` stands to BigQuery procedural SQL: a verbatim user-reported SQL block where the OSS parser chain returns nothing and GSP returns the full 3-hop ETL flow the user expected to see in the lineage UI. Both back the same v0.1.x launch claim — that the sidecar recovers procedural lineage that DataHub/OpenMetadata silently drop.

## Known limitation surfaced

- The 13 trailing `EXECUTE schName.procName` statements are observed at the call site (process id 25, `Query Insert-1` under `batchQueries`), but lineage from each invocation back into the `#tempTable` flow is not duplicated — write-target attribution remains keyed on the procedure body, not on each EXECUTE. This matches the user's expectation: lineage of `sourceTable → targetTable` should appear once in the UI, not 13 times.
