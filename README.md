# `gudusoftware/dbt-lineage`

> **Reliable column-level lineage for dbt → DataHub / OpenMetadata, where sqlglot can't reach.**
>
> Apache-2.0. dbt package + companion Python CLI. v0.0.1 (Phase 1 scaffold).

## Why

dbt's stock column-level lineage is sqlglot-based, and sqlglot silently fails on a class of dbt-real SQL constructs. Empirically (Phase 0.4 PoC, see [`materials/dbt-lineage-evidence/poc-dossier.md`](https://github.com/gudusoftware/gudu-agent-team) in the companion ops repo):

| Where sqlglot returns 0 column edges | What `gudusoftware/dbt-lineage` does |
|---|---|
| BigQuery `dbt-utils.deduplicate` macro | Resolves `all_articles → analytics.deduplicated_articles` with 5 column edges |
| BigQuery procedural SQL (DECLARE/IF/EXCEPTION/temp tables) | Traces `src → temp → tgt` with 8 column edges |
| MSSQL/T-SQL stored procedure body lineage | Traces `BEGIN ... INSERT ... SELECT ... END` end-to-end |
| T-SQL Cursor + IF/BEGIN/END control flow | Resolves all branches |

GSP wins 10 of 11 active fixtures vs sqlglot 30.6.0 (91% win rate) — see the PoC dossier. The package replaces dbt's CLL only where it fails; sqlglot output is preserved everywhere it succeeds.

## Status

**v0.0.1** — Phase 1 scaffold. Not yet on PyPI. Not yet usable end-to-end.

| Phase | Target | Schedule |
|---|---|---|
| 1 — Foundation | Manifest reader, dialect map, CLI skeleton, parser_client port, cache, CI auto-detect | 2026-05-11 → 2026-05-29 |
| 2 — M1 BigQuery + M2 MSSQL + M3 DataHub | v0.1.0 internal alpha to TestPyPI | 2026-06-01 → 2026-06-19 |
| 3 — Emitters + CI check | v0.2.0 public beta to PyPI | 2026-06-22 → 2026-07-03 |
| 4 — Hardening | v0.3.0 expanded beta | 2026-06-22 → 2026-07-03 |
| 5 — Distribution + beta validation | v1.0.0 stable | 2026-07-06 → 2026-07-24 |

See `docs/dbt-lineage/implementation-plan.md` in the companion ops repo for the full plan.

## Architecture (locked, see ADR-007)

Two halves under one repo:

1. **dbt package** (`gudusoftware/dbt_lineage`) — declarative-only macros. Installed via `packages.yml`. No runtime side effects.
2. **Python CLI** (`gsp-dbt-lineage`) — reads `target/manifest.json` post-`dbt build`, dispatches compiled SQL to GSP/SQLFlow via four backend modes (anonymous / authenticated / self-hosted Docker / local JAR), emits `target/gudu/column_lineage.json` + DataHub MCP / OpenMetadata sidecars.

## Install (planned, not yet on PyPI)

```bash
# Python CLI (when available)
pip install gsp-dbt-lineage

# dbt package
echo "packages:
  - package: gudusoftware/dbt_lineage
    version: 0.0.1" >> packages.yml
dbt deps
```

## Usage (planned)

```bash
dbt build
gsp-dbt-lineage run --backend authenticated --out target/gudu/column_lineage.json
gsp-dbt-lineage emit datahub --lineage target/gudu/column_lineage.json --out target/gudu/datahub_mcp.json
datahub ingest -c datahub_recipe.yaml
```

## Backend modes

| Mode | Where SQL goes | Volume |
|---|---|---|
| `anonymous` | `api.gudusoft.com`, no API key | 50 calls/day per IP — eval only |
| `authenticated` | `api.gudusoft.com`, personal key | 10k calls/month — Pro: 100k/day |
| `self_hosted` | Customer's own Docker container | Unlimited, data stays in VPC |
| `local_jar` | Embedded `gsp.jar` via JVM subprocess | No HTTP, no Docker |

## Known limitations

- **BigQuery UDF return STRUCT** (`func(args).*`) — both sqlglot and GSP fail. Documented in `docs/known-limitations.md`. We don't claim this as a launch fix.
- **Snowflake LATERAL FLATTEN / QUALIFY / PIVOT** — sqlglot 30.6.0 fixed these. We carry them as regression fixtures in `fixtures/evidence/_regression/` to alert if sqlglot regresses.
- **Databricks STRUCT alias / recursive CTE** — sqlglot fixed. Same regression-only treatment.
- **dbt Cloud Explorer** — no third-party plugin surface. dbt Cloud users run the CLI in their CI environment after artifact download from the dbt Cloud API.

## License

Apache-2.0. See [LICENSE](LICENSE).

## Companion repos

- [`gudusoftware/gsp-datahub-sidecar`](https://github.com/gudusoftware/gsp-datahub-sidecar) — DataHub-specific recovery sidecar (older sibling, ports patterns we reuse here)
- [`gudusoftware/gsp-openmetadata-sidecar`](https://github.com/gudusoftware/gsp-openmetadata-sidecar) — OpenMetadata equivalent
