# `_regression/` — sqlglot regression canaries

These 11 fixtures were `active` failures cited in DataHub / OpenMetadata / sqlglot issues at one point. As of sqlglot 30.6.0 the *simplified repro* of each construct passes (the original issue may have included a more elaborate scenario where edge cases still fail). We carry them as **regression canaries**: if a future sqlglot release breaks the simplified case, our CI here will turn red and we'll know we have a new active wedge.

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

1. **Pin and bisect** — pin the failing sqlglot version in `pyproject.toml [dev]` and run `pip install sqlglot==<prior>` locally; bisect to the offending sqlglot release. Note the commit/PR.
2. **File or update upstream** — open a sqlglot issue (or comment on the existing one in the canary docstring) with the pinned-version repro.
3. **Promote the row to `active`** in `materials/dbt-lineage-evidence/index.yml` (companion ops repo).
4. **Add an active fixture** under `fixtures/evidence/<row_id>_*/` with input.sql + expected_lineage.json (use `tools/build_fixtures.py`).
5. **Update launch copy** — re-run `tools/check_launch_copy.py` against README + docs + blog drafts; the linter will refuse PR merge if the row is now `regression` and still cited.
6. **Land the active fixture** in v0.x.y patch release; update CHANGELOG to call out the upstream regression.
