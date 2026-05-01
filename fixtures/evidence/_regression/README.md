# `_regression/` — sqlglot regression canaries

These 11 fixtures were `active` failures cited in DataHub / OpenMetadata / sqlglot issues at one point. As of sqlglot 30.6.0 they all pass — the parser handles them correctly. We carry them as **regression canaries**: if a future sqlglot release breaks any of them, our CI here will turn red and we'll know we have a new active wedge.

These rows are NOT marketing-eligible per `tools/check_launch_copy.py`. They are NOT part of the v1 launch claims. They exist exclusively as a tripwire.

| ID | Issue | Dialect | Construct |
|---|---|---|---|
| E07 | tobymao/sqlglot#3484 | bigquery | nested-star-expansion |
| E08 | tobymao/sqlglot#6258 | bigquery | struct-field-level-lineage |
| E09 | tobymao/sqlglot#7447 | bigquery | array-offset-with-unnest-with-offset |
| E11 | tobymao/sqlglot#3006 | snowflake | lateral-flatten-lowercase-value |
| E12 | tobymao/sqlglot#4137 | snowflake | select-star-pivot-cte |
| E13 | tobymao/sqlglot#7043 | snowflake | group-by-qualify |
| E14 | tobymao/sqlglot#6879 | databricks | struct-values-alias |
| E15 | tobymao/sqlglot#7213 | databricks | recursive-cte-keyword-preserved |
| E24 | tobymao/sqlglot#4884 | tsql | merge-inside-parens |
| E25 | tobymao/sqlglot#6033 | tsql | option-maxrecursion-on-update |
| E26 | tobymao/sqlglot#6529 | oracle | merge-conditionals |

Test runner: `tests/integration/test_sqlglot_regression_canaries.py` (Phase 4 task 4.1).

If a canary fails:
1. Promote the row to `active` in `materials/dbt-lineage-evidence/index.yml` (companion ops repo).
2. Add an active fixture under `fixtures/evidence/<row_id>_*/`.
3. Update launch copy via `tools/check_launch_copy.py` (Phase 5).
