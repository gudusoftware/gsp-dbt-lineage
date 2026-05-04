# E23b — Real user-reported T-SQL `IF EXISTS` + `GO` + `CREATE VIEW` (sqlglot#4338)

- **Source issue**: [tobymao/sqlglot#4338](https://github.com/tobymao/sqlglot/issues/4338) — "Error Converting from TSQL with IF in 1st line"
- **Reporter**: [@Palkers76](https://github.com/Palkers76) (2024-11-03)
- **Maintainer triage**: `tobymao` commented "not high priority" (2024-11-03), the issue is closed but the failure mode persists in sqlglot 30.6.0.
- **Reported SQL**: see `input.sql` — verbatim from the "Fully reproducible code snippet" in the issue body, including the leading `IF EXISTS (SELECT * FROM sys.views WHERE object_id = OBJECT_ID(N'[DBAPP].[YEARLY_TARGETS_ModelView]'))`, the three `GO` batch separators, the `SET ANSI_NULLS ON` / `SET QUOTED_IDENTIFIER ON` directives, the comment block, and the `CREATE VIEW [DBAPP].[WFA_YEARLY_TARGETS_ModelView]` body with the 9-column projection over `db.YEARLY_TARGETS_FriendlyNames T LEFT JOIN db.YEARLY_TARGETS_DIVISION_FriendlyNames D`.
- **Dialect targeted by reporter**: T-SQL / Synapse SQL
- **Parser chain tested**: `sqlglot` → `sqlfluff` → `sqlparse` via `collate-sqllineage 2.1.1` (the same chain OpenMetadata's lineage ingestion uses); also direct `sqlglot.parse_one(sql, read="tsql")` and `sqlglot.lineage.lineage(...)`.
- **GSP version tested**: local JAR `gsqlparser-4.1.0.15-shaded.jar`
- **Cached GSP response**: `materials/dbt-lineage-evidence/poc-responses/E23b_response.json`

## Verified claim

| Metric | OpenMetadata CLL chain (sqlglot 30.6.0 → sqlfluff → sqlparse, via collate-sqllineage 2.1.1) | Direct `sqlglot.parse_one(read='tsql')` | GSP/SQLFlow 4.1.0.15 |
|---|---|---|---|
| Parser status | `unsupported` (`UnsupportedStatementException` on the `[alias]` token at the IF EXISTS line) | parses to a single `IfBlock`; rest of the batch is silently dropped — `find_all(exp.Create)` returns nothing | `parsed` — IF/DROP/GO header is consumed, `CREATE VIEW` body is fully analyzed |
| Real upstream tables | 0 | 0 (the `Create` node is gone from the AST) | 3 (`db.YEARLY_TARGETS_FriendlyNames`, `db.YEARLY_TARGETS_DIVISION_FriendlyNames`, `sys.views`) plus the view itself |
| Write target | n/a | n/a | `[DBAPP].[WFA_YEARLY_TARGETS_ModelView]` (1 write target, 1 process) |
| Column edges | 0 | 0 (`lineage()` raises `SqlglotError: Cannot build lineage, sql must be SELECT`) | 6 column-level edges across 4 of the view's 9 output projections (`PROD_HIER:_DIVISION_CODE_FDR`, `TARGET_DIVISION`, `OBJECT_ID`, plus the `*` wildcard from the IF EXISTS probe) |
| Honest unresolved set | n/a | n/a | 5 view columns reported as `confidence=low, upstream=[]` because the user wrote them unqualified (`[Target_Division_Sort], [Target_0_Percent], …`) and GSP flagged them as orphan columns rather than fabricating an upstream binding. |

## Parallel to E04b and E16b

This fixture stands to T-SQL `IF EXISTS` / `GO` / `CREATE VIEW` deployment scripts as
`E04b_bigquery_procedural_real_datahub_11654` stands to BigQuery procedural SQL and
`E16b_mssql_stored_proc_real_openmetadata_25299` stands to MSSQL `CREATE PROCEDURE … BEGIN … END`
wrappers: a verbatim user-reported SQL block where every parser in the OpenMetadata
default CLL chain returns nothing and GSP returns the real ETL chain. All three back the
same v0.1.x launch claim — that the sidecar recovers lineage that DataHub/OpenMetadata
silently drop on real, in-the-wild SQL.

## Honesty notes

- 5 of the 9 view output columns (`Target_Division_Sort`, `Target_0_Percent`,
  `Target_50_Percent`, `Target_100_Percent`, `Target_100_Attainment_Percent`,
  `Target_150_Percent`, `Target_Division_Sort`, `Year`) are written *unqualified*
  in the reporter's SQL (no `T.` or `D.` prefix). GSP flags these as orphan columns
  in its `errors` block (`find orphan column(10500) near: [Target_Division_Sort](14,8)` etc.)
  and the mapper records them as `confidence=low, upstream=[]` rather than guessing.
  This is the "richer `evidence` and `unresolved` output" the v0.1.x launch claim
  promises — we do **not** fabricate an upstream we cannot prove.
- The `IF EXISTS` probe touches `sys.views`, so `sys.views` legitimately appears in
  `upstream_tables` even though it is part of the deployment-time existence check
  rather than the production read path. Reviewers who care about the production
  read path should consult the `evidence` block once the `views` collection lands
  in `evidence.procedural` (planned follow-up).
- This fixture was discovered via the sqlglot issue tracker rather than a
  data-catalog issue tracker (DataHub/OpenMetadata) because the failure mode
  manifests at the parser layer that both catalogs share. The `current_oss_behavior.json`
  baseline confirms `collate-sqllineage 2.1.1` (OpenMetadata's installed chain) hits the
  same `UnsupportedStatementException` on the same SQL.
