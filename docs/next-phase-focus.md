# Next Phase Focus — gsp-dbt-lineage

**Date:** 2026-05-03  
**Status:** current planning baseline after v0.1.0-alpha status calibration  
**Scope:** `gsp-dbt-lineage` repo, companion implementation plan, Obsidian SQL Governance KB, and the current GSP Java Semantic IR roadmap.

## 1. One-sentence direction

The next phase should move `gsp-dbt-lineage` from an end-to-end alpha sidecar into a trustable dbt column-lineage workflow: keep the current dbt-artifact adapter boundary, harden column-level correctness evidence, add semantic diff and slim-CI support, and prepare for the future GSP Java Semantic IR / canonical lineage model without making the dbt package depend on unfinished IR work.

## 2. Current implementation baseline

As inspected on 2026-05-03:

- Repo branch: `master`.
- Latest repo commit: `81acd8d Phase A: status calibration to v0.1.0-alpha`.
- Test command:
  ```bash
  . .venv/bin/activate && pytest -q tests/unit tests/integration
  ```
- Result: **191 tests passed**.
- Runtime status:
  - `gsp-dbt-lineage run` is implemented, including non-dry-run backend dispatch.
  - Backend modes are wired: `anonymous`, `authenticated`, `self_hosted`, `local_jar`.
  - `emit datahub` is implemented.
  - `emit openmetadata` is experimental / beta.
  - `check` and `diff` exist, but baseline comparison is still node-edge-count based, not per-column semantic diff.
  - Selectors `--select`, `--exclude`, and `--resource-type` exist; dbt `--state` / `state:modified+` is still planned.
  - Output schema supports `confidence` and `unresolved`; mapper currently emits basic confidence and unresolved parser failures, but not rich evidence blocks.

## 3. Relevant GSP Java status

The GSP Java roadmap has moved beyond slice 12:

- Slice 12 set operations were merged to master via PR #609.
- Current active GSP Java branch inspected: `semantic-ir-slice13-window-functions`.
- Uncommitted slice-13 work adds a `WindowSpec` model and per-output `window` JSON field, with window-function projection support under development.
- Existing Semantic IR state after slice 12: 10-SQL frozen corpus, zero divergences against the dlineage comparison harness, and 137 Semantic IR tests documented in the roadmap.

Implication for `gsp-dbt-lineage`:

- Do **not** block dbt-side work on Semantic IR slice 13, because production lineage is still `dlineage` / SQLFlow authoritative.
- Do prepare the `column_lineage.json` schema and mapper boundaries for future richer facts: window dependencies, filter/join/control influence, canonical lineage classes, evidence, and diagnostics.
- Keep `gsp-dbt-lineage` as an adapter and workflow product, not as a second lineage engine.

## 4. Next-phase priorities

### P0 — Correctness and evidence gates for v0.1.x

Goal: make the alpha credible on the exact wedges it claims.

1. Keep marketing and docs evidence-gated:
   - BigQuery `dbt-utils.deduplicate`;
   - BigQuery procedural SQL;
   - MSSQL stored procedures;
   - T-SQL cursor / IF / BEGIN / END.
2. Expand active fixtures only where GSP/SQLFlow demonstrably beats sqlglot today.
3. Keep Snowflake / Databricks cases as regression canaries unless sqlglot regresses.
4. Preserve the E06 limitation: BigQuery UDF return STRUCT `func(args).*` is not a launch claim until GSP grammar supports it.
5. Add richer `evidence` and `unresolved` output for partial / failed nodes so users can understand exactly what was trusted and what was not.

#### P0 status — MSSQL stored procedures (2026-05-03)

- **Headline fixture promoted from toy SQL to real user-reported SQL.** New
  fixture `E16b_mssql_stored_proc_real_openmetadata_25299` carries the
  verbatim SQL from
  [open-metadata/OpenMetadata#25299](https://github.com/open-metadata/OpenMetadata/issues/25299)
  (`CREATE PROCEDURE schName.procName AS BEGIN ... END` with a 3-hop
  temp-table chain `schName.sourceTable → #tempTable → schName.targetTable`,
  plus the full `CREATE database / schema / table` setup the reporter pasted
  and the 13 trailing `EXECUTE schName.procName` calls). All six
  integration-gauntlet checks pass; mapper round-trip stable; deterministic
  render verified. Reporter confirms the OpenMetadata CLL chain
  (`sqlglot → sqlfluff → sqlparse`) returns zero column edges across
  versions 1.10.0, 1.10.4, and 1.11.2 — a cleaner differential than the
  toy E16/E17/E18 trio, which only minimally repro the same wrapper.
- **Mapper emits `evidence.procedural` unchanged on MSSQL.** The
  procedural-evidence emitter that landed for E04b is dialect-agnostic; on
  E16b it records 2 write targets (`#tempTable ← sourceTable`,
  `targetTable ← #tempTable`), 2 column edges (`columnName → columnName` on
  each hop), 3 processes (the two procedure-body INSERTs plus the outer
  batch-query INSERT), and preserves GSP's `subType: temp_table` marker on
  `#tempTable`. No mapper code change was needed for the MSSQL wedge.
- **Stock dbt CLL on the verbatim SQL: 0 edges.** PR #14586 removed the
  `LIKE '%create%procedure%'` ingestion filter, so the procedure text now
  reaches the parser chain — but each parser bails on the
  `CREATE PROCEDURE … BEGIN … END` wrapper before reaching the inner
  `INSERT` statements. This matches the symptom reporters describe in
  #25299 (and in the related #16737 / #17586) after the filter fix.
- **Cached response: local JAR.** Captured via
  `gsqlparser-4.1.0.15-shaded.jar` and stored at
  `materials/dbt-lineage-evidence/poc-responses/E16b_response.json` in the
  `{http_status, body: {code, data: {sqlflow}}}` cloud shape so
  `LocalJarBackend` and `AnonymousBackend`/`AuthenticatedBackend` paths
  share the same cached fixture surface.
- **Evidence-index updated.** `materials/dbt-lineage-evidence/index.yml`
  carries E16b alongside E04b as the launch-claim-eligible MSSQL row.
- **Open question for the cloud-side bug log.** Cloud
  `exportFullLineageAsJson` was not retried for the verbatim
  multi-statement-with-`go`-batch-separator SQL on this round; the local
  JAR path is sufficient for the cached PoC pipeline. Add to the watch list
  if anonymous/authenticated mode regresses on T-SQL batch separators.

#### P0 status — BigQuery procedural (2026-05-03)

- **Headline fixture promoted from toy SQL to real user-reported SQL.** New
  fixture `E04b_bigquery_procedural_real_datahub_11654` carries the verbatim
  SQL from
  [datahub-project/datahub#11654](https://github.com/datahub-project/datahub/issues/11654)
  (DECLARE STRUCT<…ARRAY<DATE>>, CALL with tuple args, nested IF, CREATE OR
  REPLACE TEMP TABLE, SELECT * EXCEPT, WHERE (a,b,c,d) IN UNNEST(…)). All six
  integration-gauntlet checks pass; mapper round-trip stable; deterministic
  render verified. sqlglot 30.6.0 raises hard `ParseError` on this SQL — a
  cleaner differential than the toy E04, which only falls back to Command.
- **Mapper now emits `evidence.procedural`** with per-write-target attribution
  (`write_targets`, `write_target_count`, `column_edge_count`,
  `process_count`). For E04b this records 2 write targets and 11 column
  edges, matching the published #11654 reply and the `dpriver.com` blog
  walkthrough.
- **Mapper now filters GSP synthetic helper columns** (`COUNT`, `COUNT(N)`,
  `RELATIONROWS`) that GSP emits when an `IF (SELECT COUNT(N) FROM …)`
  predicate or WHERE/ORDER BY clause is present. This matches the existing
  filter for T-SQL `@`-prefixed locals.
- **Two GSP-related bugs uncovered while wiring E04b**:
  1. `LocalJarBackend` returned `{code, data: <dataflow>}` while
     `lineage_mapper.map_gsp_to_node` expects `data.sqlflow.*` (cloud shape).
     Net effect: any user running `--backend local_jar` got empty lineage.
     Fixed in `parser_client.py`; locked with two unit tests.
  2. `https://api.gudusoft.com/.../exportFullLineageAsJson` returns
     `HTTP 500 — Export full lineage error` on the E04b SQL, even though
     the local JAR (`gsqlparser-4.1.0.15-shaded.jar`) parses the same SQL
     fine. **Open GSP cloud-side bug.** The fixture's cached response was
     captured via the local JAR as a workaround. Fix would let the cached
     PoC pipeline use anonymous/authenticated mode for this case again.

### P1 — Column-level semantic diff for v0.2 beta

Current `check` / `diff` detects edge-count regressions by node. The next useful CI feature is a column-semantic diff that reports exactly which downstream column lost which upstream dependency.

Recommended output shape:

```json
{
  "node_id": "model.pkg.orders",
  "column": "net_revenue",
  "lost_upstream": [{"table": "raw.orders", "column": "discount_amount"}],
  "added_upstream": [],
  "severity": "regression"
}
```

Implementation notes:

- Diff by `(node_id, column.name, upstream.table, upstream.column)` rather than only by aggregate edge counts.
- Treat `status` regressions (`parsed -> partial/failed/unsupported`) as high severity.
- Keep count-based summary for quick CI output, but add JSON output for PR comments and debugging.
- Add fixture pairs that prove renamed columns, lost upstreams, and false positives are distinguishable.

### P2 — Slim CI / dbt state support

Add `--state` / `state:modified+` support so users can run lineage only for changed dbt nodes plus their downstream dependents.

Recommended behavior:

- Accept `--state path/to/previous/artifacts`.
- Reuse dbt manifest metadata and parent/child maps to select modified nodes.
- Make `state:modified+` mean “modified nodes plus downstream graph”.
- Cache unchanged SQL by SQL hash and parser version.
- Document interaction with `--select` / `--exclude`.

### P3 — Catalog-emitter hardening

For DataHub and OpenMetadata:

- Keep DataHub MCP as the primary implemented emitter.
- Keep OpenMetadata marked BETA until a first-class ingestion source or validation loop exists.
- Add emitter tests for service/platform mapping, casing, and missing upstream tables.
- Plan a future `--validate-against-om` or equivalent live-catalog validation step before claiming production OpenMetadata ingestion.

### P4 — Future canonical lineage / Semantic IR alignment

Do not redesign the public dbt sidecar schema around unfinished Semantic IR internals yet. Instead:

- Keep `column_lineage.json` additive and tolerant of future fields.
- Add optional fields only when they have stable semantics:
  - `evidence`;
  - `influence` / `influence_type` for filter, join, group, order, window, control;
  - `parser_diagnostics`;
  - future `canonical_lineage_version`.
- Map from GSP Java / SQLFlow outputs into this schema; do not make dbt-specific schema the upstream IR.

## 5. Explicit non-goals

- Do not parse raw Jinja SQL.
- Do not mutate `manifest.json`.
- Do not become a full dbt platform or dbt Cloud Explorer replacement.
- Do not advertise broad Snowflake / Databricks parser superiority without current evidence.
- Do not replace GSP Java `dlineage` or Semantic IR work inside this Python repo.

## 6. Recommended immediate task list

1. Implement per-column semantic diff and update `check --fail-on-regression` to use it.
2. Add JSON diff output suitable for PR comments.
3. Add `--state` / slim-CI selectors.
4. Populate richer `evidence` / `unresolved` fields in `column_lineage.json`.
5. Keep docs aligned: README, quickstart, CI docs, known limitations, and companion KB notes.
6. Revisit PyPI only after v0.2 beta CI workflows and documentation are stable.
