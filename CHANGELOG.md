# Changelog

All notable changes to `gudusoftware/gsp-dbt-lineage` will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Schema: [SemVer](https://semver.org/).

## [Unreleased]

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
