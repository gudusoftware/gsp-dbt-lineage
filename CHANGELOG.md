# Changelog

All notable changes to `gudusoftware/gsp-dbt-lineage` will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Schema: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Richer `evidence` and `unresolved` output for partial / failed nodes
  (P0 §5 of `docs/next-phase-focus.md`):
  - `evidence.parser_diagnostics` surfaces GSP `errors`-block hints
    (e.g. `find orphan column(10500) near: [Year](20,8)`) with type, message,
    GSP-side spelling (`near_column`), and source line/col.
  - Each column without a resolved upstream now produces a node-level
    `unresolved` entry. Reasons:
    - `parser_orphan_column` — GSP flagged the column as orphan.
      Carries `target_column`, `line`, `col`, `parser_message`.
    - `upstream_unresolved` — GSP saw the column but the mapper could not
      trace it (typical of multi-hop CASE-WHEN / derived expressions).
      Carries `target_column`.
    - `parser_syntax_hint` — non-orphan parser hint (e.g. unexpected token).
      Carries `parser_message` and optional `line`/`col`.
    - `source_table_unknown` — relationship pointed at an unknown parent.
      Pre-existing reason; preserved unchanged.
  - On E23b (sqlglot#4338): all 7 GSP orphan-column hints surface, plus the
    case-when-derived column the mapper cannot multi-hop through.
  - **Failed-node contract** (status=`failed` / `skipped`): these never
    reach the mapper, so they carry no `evidence` block. The
    `unresolved` array is the receipt — `parser_error`, `quota_limited`,
    `compiled_sql_unreadable`, `skipped` entries each include a `reason`
    and a `detail` field where applicable. This is by design: there is no
    GSP response to extract diagnostics from when parse never happened.

### Changed
- `_extract_parser_diagnostics` is now defensive against malformed GSP
  payloads (non-list `errors`, non-dict entries, dict-typed
  `originCoordinates`); prior versions would raise on shape drift seen
  between cloud and local-jar backends.
- Orphan-column matching tries exact column name first, then uppercase
  fallback — so case-sensitive quoted identifiers don't collapse onto
  same-spelling neighbors.

## [0.1.0a0] - 2026-05-03

### Added
- Phase 2 — M1 BigQuery + M2 MSSQL stored procedures + M3 DataHub emitter wired.
- Phase 3 — OpenMetadata emitter (BETA), `check`, `diff`, GitHub Action.
- Phase 4 — Regression-fixture corpus (sqlglot canaries), JVM extras, launch-copy linter.
- Runnable end-to-end demo at `docs/examples/` — synthetic one-model dbt manifest with real `column_lineage.json` produced by anonymous-tier API call.
- README rewrite: capability table (implemented / experimental / planned), roadmap (Phase A status calibration → D distribution), evidence-gated marketing.

### Changed
- Marketing scope tightened: only BigQuery `dbt-utils.deduplicate`, BigQuery procedural SQL, MSSQL/T-SQL stored proc + cursor wedges are advertised as parser-superiority over sqlglot 30.6.0. Snowflake and Databricks fixes are explicitly disclaimed (sqlglot fixed them; we carry regression canaries only).

### Known limitations
- `check` / `diff` regression detection is at node-edge-count granularity; per-column semantic diff is planned for v0.2 beta.
- OpenMetadata emitter is BETA — schema is stable but no first-class `metadata ingest` source plugin yet.

## [0.0.1] - 2026-05-01

### Added
- Repository scaffold (Phase 1 task 1.1).
- ADR-007 architecture decision (companion repo `gudusoftware/gudu-agent-team`).
