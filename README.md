# `gudusoftware/gsp-dbt-lineage`

> **Reliable column-level lineage for dbt → DataHub / OpenMetadata, where sqlglot can't reach.**
>
> Apache-2.0. dbt package + companion Python CLI. **v0.1.0-alpha** — end-to-end usable, not yet on PyPI.

## Why

dbt's stock column-level lineage is sqlglot-based, and on a narrow set of dbt-real SQL constructs sqlglot silently returns zero column edges. Empirically (Phase 0.4 PoC, 10 wins of 11 active fixtures — see [`materials/dbt-lineage-evidence/poc-dossier.md`](https://github.com/gudusoftware/gudu-agent-team) in the companion ops repo):

| Where sqlglot returns 0 column edges | What `gudusoftware/gsp-dbt-lineage` does |
|---|---|
| BigQuery `dbt-utils.deduplicate` macro | Resolves `all_articles → deduplicated_articles` with 3 column edges (see [`docs/examples/column_lineage.json`](docs/examples/column_lineage.json)) |
| BigQuery procedural SQL (DECLARE STRUCT, CALL, nested IF, CREATE TEMP TABLE) | Recovers 2 write targets and 11 column edges on the real user-reported [datahub#11654](https://github.com/datahub-project/datahub/issues/11654) script — see [`fixtures/evidence/E04b_bigquery_procedural_real_datahub_11654/`](fixtures/evidence/E04b_bigquery_procedural_real_datahub_11654/). sqlglot 30.6.0 raises `ParseError` on the same SQL. |
| MSSQL/T-SQL stored procedure body lineage | Traces `BEGIN ... INSERT ... SELECT ... END` end-to-end |
| T-SQL Cursor + IF/BEGIN/END control flow | Resolves all branches |

The package replaces dbt's CLL only where sqlglot returns nothing; sqlglot output is preserved everywhere it succeeds. We do **not** claim Snowflake or Databricks dialect coverage — sqlglot 30.6.0 fixed those constructs. They live in `fixtures/evidence/_regression/` as canaries against a sqlglot regression.

## Status

**v0.1.0-alpha** — end-to-end usable on a real dbt manifest (run + emit + check + diff all wired). Not yet on PyPI; install from source. See [`docs/examples/`](docs/examples/) for a runnable one-model demo and the real `column_lineage.json` it produces.

| Capability | Status | Notes |
|---|---|---|
| `gsp-dbt-lineage run` (manifest → column_lineage.json) | **implemented** | All 4 backend modes wired; cache, redaction, CI guard, retries in. |
| `gsp-dbt-lineage emit datahub` (MCP-compatible payload) | **implemented** | Round-trip example in `docs/examples/datahub_mcp.json`. |
| `gsp-dbt-lineage emit openmetadata` (AddLineageRequest) | **experimental (BETA)** | Schema is stable but no first-class `metadata ingest` source plugin yet — wrap in your own POST loop or wait for Phase 4. |
| `gsp-dbt-lineage check` (CI gate: coverage / regression / unsupported) | **implemented** | Node-edge-count regression detection. Column-level diff is **planned** — see [Roadmap](#roadmap). |
| `gsp-dbt-lineage diff` (baseline comparison) | **implemented** | Same caveat as `check` — node-level edge count, not per-column semantic diff (planned). |
| `gsp-dbt-lineage doctor` (env diagnostics) | **implemented** | |
| dbt-side macros (`packages.yml`) | **implemented (optional)** | Declarative-only; most users skip. |
| GitHub Action wrapper | **implemented** | `action.yml` at repo root. |
| Selectors `--select` / `--exclude` / `--resource-type` | **implemented** | |
| `--state` / `state:modified+` (slim CI) | **planned** | Phase C / v0.2 beta. |
| Per-column semantic diff (which column lost which upstream) | **planned** | Phase C / v0.2 beta. |
| PyPI publication | **planned** | Phase D / v1.0. |
| `confidence` / `unresolved` evidence in output | **partial** | Schema supports it; mapper currently emits `confidence: high` for parsed nodes and dynamic-SQL warnings, no `evidence` block yet. |

### Roadmap

| Phase | Target | Notes |
|---|---|---|
| **A — Status calibration** | Docs ↔ code parity, runnable example, evidence-gated marketing | Complete in repo baseline `81acd8d`. |
| **B — Wedge alpha (current focus)** | BigQuery `dbt-utils.deduplicate`, BigQuery procedural, MSSQL stored procs end-to-end with richer `evidence` / `unresolved` / `confidence` populated | v0.1.x |
| C — CI/CD beta | Per-column semantic diff, `--state` / slim CI, sticky PR comment, Docker GitHub Action | v0.2.x |
| D — Distribution + enterprise POC | PyPI release, canonical lineage model, filter / join / control influence separation, PII tag propagation | v1.0 |

See [`docs/next-phase-focus.md`](docs/next-phase-focus.md) for the current repo-level focus and `docs/dbt-lineage/implementation-plan.md` in the companion ops repo for the full historical runbook.

## Architecture (locked, see ADR-007)

Two halves under one repo:

1. **dbt package** (`gudusoftware/gsp_dbt_lineage`) — declarative-only macros. Installed via `packages.yml`. No runtime side effects.
2. **Python CLI** (`gsp-dbt-lineage`) — reads `target/manifest.json` post-`dbt build`, dispatches compiled SQL to GSP/SQLFlow via four backend modes (anonymous / authenticated / self-hosted Docker / local JAR), emits `target/gudu/column_lineage.json` + DataHub MCP / OpenMetadata sidecars.

## Install

PyPI release is **planned** (Phase D / v1.0). Until then, install from source:

```bash
git clone https://github.com/gudusoftware/gsp-dbt-lineage.git
cd gsp-dbt-lineage
python -m venv .venv && . .venv/bin/activate
pip install -e .
```

The dbt-side package (`gudusoftware/gsp_dbt_lineage`) is **optional** — only needed if you want `gudu_lineage` config exposed to the manifest:

```yaml
# packages.yml — optional
packages:
  - package: gudusoftware/gsp_dbt_lineage
    version: 0.1.0
```

## Usage

A real, runnable example lives in [`docs/examples/`](docs/examples/) — one synthetic BigQuery model with a real `column_lineage.json` produced by an anonymous-tier API call.

```bash
dbt build
gsp-dbt-lineage run --backend authenticated --out target/gudu/column_lineage.json
gsp-dbt-lineage emit datahub --lineage target/gudu/column_lineage.json --out target/gudu/datahub_mcp.json
datahub ingest -c datahub_recipe.yaml
```

## Development / running tests

The repo's tests assume a venv with the package and dev dependencies installed:

```bash
. .venv/bin/activate
pytest -q tests/unit tests/integration
# 191 passed
```

Running pytest against the system Python will fail because `sqlglot` and the editable install live in `.venv`.

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
