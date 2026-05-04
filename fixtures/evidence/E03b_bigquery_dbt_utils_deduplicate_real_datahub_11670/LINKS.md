# E03b — Real user-reported BigQuery `dbt-utils.deduplicate` (datahub#11670)

- **Source issue**: [datahub-project/datahub#11670](https://github.com/datahub-project/datahub/issues/11670) — "dbt/BigQuery: Incomplete Column Level Lineage when using deduplication macros"
- **Reporter**: [@Starkie](https://github.com/Starkie) (Adriano Vega Llobell), 2024-10-18
- **Reported SQL**: see `input.sql` — verbatim from the "Describe the bug" code block in the issue body, including the `unique` alias (BigQuery reserved-word edge case), lowercase keywords, the missing `AS` keyword on `[offset(0)] unique` and `from all_articles original`, and the original whitespace inside the `array_agg` call.
- **Reproduction repo provided by reporter**: <https://github.com/Starkie/datahub-dbt-lineage-repro>
- **Reporter's confirmed symptom**: "the column-level lineage (CLL) is missing for some of the datasets. The table-level lineage is fine for all of them."
- **DataHub version impact**: `0.14.1` and `acryl-datahub` `0.14.1` per the issue body; the same `dbt_utils.deduplicate` macro ships unchanged in dbt-utils 1.x and continues to fail with current `acryl-datahub` builds.
- **Parser chain tested**: `sqlglot 30.6.0` direct + `collate-sqllineage 2.1.1` → `collate-sqlfluff 3.5.2` → `sqlparse 0.5.3` (the same chain DataHub's CLL ingestion uses when `prefer_sql_parser_lineage=true`).
- **GSP version tested**: local JAR `gsqlparser-4.1.0.15-shaded.jar` (cloud `exportFullLineageAsJson` not retried for this fixture; local JAR is sufficient and matches the E04b/E16b/E23b cached-PoC convention).
- **Cached GSP response**: `materials/dbt-lineage-evidence/poc-responses/E03b_response.json`
- **Companion engagement**: James posted a sidecar reply on this issue 2026-05-03; see project memory `project_datahub_engagement_targets`.

## Verified claim

| Metric | Direct `sqlglot 30.6.0` | OpenMetadata CLL chain (`collate-sqllineage 2.1.1`) | GSP/SQLFlow 4.1.0.15 |
|---|---|---|---|
| Parser status | parses to `Select` (no error) | `partial` — table lineage found, column lineage empty | `parsed` |
| Source tables | n/a (column-level path is the failure) | 1 (`all_articles`) | 1 (`all_articles`) |
| Column edges | 0 — `lineage('article_name', sql, dialect='bigquery')` raises `SqlglotError: Cannot find column 'article_name' in query.` | 0 — `runner.get_column_lineage()` returns `[]` | 3 — outermost `unique.*` projection traces to `all_articles.*`, `all_articles.ARTICLE_NAME`, `all_articles.ID` (the latter two via the inner `ARRAY_AGG(... ORDER BY article_name)` and `GROUP BY id`) |
| Reporter symptom reproduced | yes | yes | n/a — GSP recovers what reporter expected |

## Parallel to E04b, E16b, and E23b

This fixture stands to BigQuery `dbt-utils.deduplicate` as
`E04b_bigquery_procedural_real_datahub_11654` stands to BigQuery procedural SQL,
`E16b_mssql_stored_proc_real_openmetadata_25299` stands to MSSQL `CREATE PROCEDURE … BEGIN … END`
wrappers, and `E23b_t_sql_if_exists_multi_statement_real_sqlglot_4338` stands to T-SQL
`IF EXISTS` / `GO` / `CREATE VIEW` deployment batches: a verbatim user-reported SQL
block where the OpenMetadata CLL chain's column-level lineage panel is empty and
GSP returns the column lineage the user expected to see. Together the four `*b`
fixtures form the v0.1.x evidence-gated launch claim — one wedge per dialect family,
each backed by a real user pasting their actual SQL into a public issue tracker.

## Difference from E03 (toy)

The toy `E03` fixture replaces `unique` with `u` and the lowercase keywords with
uppercase — a clean but slightly altered repro. `E03b` is the *exact* SQL from the
issue body, preserving:

1. `unique` as alias (BigQuery treats this as a reserved word in some contexts;
   keeping it confirms GSP resolves the column reference past the keyword conflict).
2. Lowercase SQL keywords (the way real dbt-compiled output looks).
3. Missing `AS` on `[offset(0)] unique` and `from all_articles original` — both
   legal BigQuery syntax variants the reporter actually wrote.
4. Original whitespace and line breaks inside the `array_agg(...)` call.

Both fixtures resolve to the same lineage chain (1 upstream table, 3 column edges
into the `*` projection) — the launch claim is unchanged. `E03b` is the one cited
in marketing, blog walkthroughs, and the sidecar reply on the issue.
