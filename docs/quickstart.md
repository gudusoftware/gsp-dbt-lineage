# Quickstart — `gudusoftware/gsp-dbt-lineage`

Three steps from zero to column-lineage in your DataHub or OpenMetadata catalog.

## 1. Install

The runtime CLI is a single `pip install`:

```bash
pip install gsp-dbt-lineage
```

The dbt-side package (`gudusoftware/gsp_dbt_lineage`) is **optional** — install it only if you want to expose `gudu_lineage` config to the manifest via dbt vars. Most users skip this step:

```yaml
# packages.yml — only if you want dbt-side config exposure
packages:
  - package: gudusoftware/gsp_dbt_lineage
    version: 0.0.1
```

```bash
dbt deps
```

## 1b. Get a backend identity (for any non-eval use)

The CLI defaults to the **anonymous tier** (50 calls/day per IP) — fine for evaluation. For routine use you need credentials:

- **Personal API key (free, 10k/month):** sign up at [docs.gudusoft.com/sign-up](https://docs.gudusoft.com/sign-up/). Set `GSP_USER_ID` and `GSP_SECRET_KEY` env vars.
- **Self-hosted / air-gapped:** see [`docs/backend-modes.md`](backend-modes.md).

## 2. Run after `dbt build`

Linux / macOS:
```bash
dbt build
gsp-dbt-lineage run \
    --manifest target/manifest.json \
    --backend authenticated \
    --user-id "$GSP_USER_ID" \
    --secret-key "$GSP_SECRET_KEY" \
    --out target/gudu/column_lineage.json
```

Windows (PowerShell):
```powershell
dbt build
gsp-dbt-lineage run `
    --manifest target/manifest.json `
    --backend authenticated `
    --user-id $env:GSP_USER_ID `
    --secret-key $env:GSP_SECRET_KEY `
    --out target/gudu/column_lineage.json
```

Output:

```
wrote target/gudu/column_lineage.json — 240 parsed, 5 partial, 1 failed, 0 skipped, coverage 95%
```

For evaluation use `--backend anonymous` (50 calls/day per IP).

## 3. Emit to DataHub or OpenMetadata

### DataHub

```bash
gsp-dbt-lineage emit datahub \
    --lineage target/gudu/column_lineage.json \
    --out target/gudu/datahub_mcp.json

datahub ingest -c datahub_recipe.yaml
```

A minimal `datahub_recipe.yaml`:

```yaml
source:
  type: file
  config:
    path: target/gudu/datahub_mcp.json

sink:
  type: datahub-rest
  config:
    server: 'http://localhost:8080'
```

### OpenMetadata (BETA)

```bash
gsp-dbt-lineage emit openmetadata \
    --lineage target/gudu/column_lineage.json \
    --out target/gudu/openmetadata_lineage.json
```

Each array entry uses `fullyQualifiedName` for the entity reference, which OpenMetadata resolves to a UUID at ingest time. Two ways to ingest:

**A. OpenMetadata `metadata` CLI (recommended):** wrap the file in a custom ingestion source. The simplest pattern is to POST each entry yourself with a 5-line Python script:

```python
import json, requests
OM = "http://your-om:8585/api/v1"
TOKEN = "<your jwt>"
for req in json.load(open("target/gudu/openmetadata_lineage.json")):
    r = requests.put(f"{OM}/lineage", json=req, headers={"Authorization": f"Bearer {TOKEN}"})
    r.raise_for_status()
```

**B. Custom OpenMetadata source plugin** (production): see `docs/known-limitations.md` §6. Phase 4 ships a first-class `metadata ingest`-compatible adapter.

## 4. CI gate — `check`

In your CI pipeline:

```bash
gsp-dbt-lineage check \
    --lineage target/gudu/column_lineage.json \
    --min-node-coverage 0.95 \
    --baseline target/gudu/column_lineage.prev.json \
    --fail-on-regression
```

This exits non-zero if:
- Less than 95% of eligible nodes parsed.
- Any node lost column-lineage edges relative to `--baseline`.
- Any node has `status: failed` (auto-applied in CI environments).

A drop-in GitHub Action lives at `gudusoftware/gsp-dbt-lineage` — see `docs/ci-integration.md`.

## Backend modes

| Mode | Volume | Where SQL goes |
|---|---|---|
| `anonymous` | 50/day per IP | `api.gudusoft.com` |
| `authenticated` | 10k/month free, 100k/day Pro | `api.gudusoft.com` (you authenticate) |
| `self_hosted` | unlimited | your own Docker container |
| `local_jar` | unlimited, no HTTP | embedded JVM subprocess |

## Diagnostics

```bash
gsp-dbt-lineage doctor --backend authenticated
```

Output:

```
  [OK] python       Python 3.11.5 (OK)
  [OK] dbt          dbt found at /usr/local/bin/dbt
  [OK] manifest     target/manifest.json OK — dbt 1.7.4, adapter bigquery, 240 nodes
  [OK] environment  CI detected: False
  [OK] backend      authenticated reachable: ...

5 ok, 0 failed.
```

## What this package fixes

dbt's stock column-level lineage is sqlglot-based, and sqlglot silently fails on:

- BigQuery `dbt-utils.deduplicate` macro
- BigQuery procedural SQL (DECLARE/IF/EXCEPTION/temp tables)
- MSSQL/T-SQL stored procedure body lineage
- T-SQL Cursor + IF/BEGIN/END

Where sqlglot returns 0 column edges, this package routes the same compiled SQL through GSP/SQLFlow, which traces the body end-to-end. See `materials/dbt-lineage-evidence/poc-dossier.md` (companion ops repo) for the 91% win-rate dossier.

## What this package doesn't fix

- BigQuery UDF return STRUCT (`func(args).*`) — known limitation; documented in `docs/known-limitations.md`.
- Snowflake LATERAL FLATTEN, Databricks STRUCT alias, etc. — sqlglot 30.6.0 fixed these. Carried as regression fixtures in `fixtures/evidence/_regression/`.

See `docs/known-limitations.md` for the full list.
