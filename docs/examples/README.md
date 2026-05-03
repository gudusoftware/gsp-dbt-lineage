# End-to-end example — minimal dbt project

This directory holds a real, runnable end-to-end demo of `gsp-dbt-lineage`. It is the proof that the CLI is wired all the way through `run` → `emit datahub` → `emit openmetadata` → `check` → `diff`.

The `column_lineage.json` here was produced by a live call to the anonymous tier of `api.gudusoft.com` on 2026-05-03 against a one-model synthetic manifest. The compiled SQL is the dbt-utils `deduplicate` macro output on BigQuery (fixture E03), which sqlglot 30.6.0 cannot resolve to any column edges.

## Files

| File | What it is |
|---|---|
| `minimal_dbt_project_manifest.json` | A one-model synthetic dbt manifest (BigQuery adapter). `compiled_code` is the E03 dbt-utils.deduplicate macro output. |
| `column_lineage.json` | Real output of `gsp-dbt-lineage run --backend anonymous`. 1 model parsed, 3 column edges resolved against `all_articles`. |
| `datahub_mcp.json` | DataHub MCP-compatible payload from `emit datahub`. Ingest with `datahub ingest -c <recipe>` pointing at this file. |
| `openmetadata_lineage.json` | OpenMetadata `AddLineageRequest` payload from `emit openmetadata` (BETA). |

## Reproduce

```bash
. .venv/bin/activate

# 1. Parse compiled SQL → column_lineage.json (one anonymous-tier API call)
gsp-dbt-lineage run \
    --manifest docs/examples/minimal_dbt_project_manifest.json \
    --backend anonymous \
    --out docs/examples/column_lineage.json \
    --deterministic --no-cache

# 2. Convert to DataHub MCPs
gsp-dbt-lineage emit datahub \
    --lineage docs/examples/column_lineage.json \
    --out docs/examples/datahub_mcp.json

# 3. Convert to OpenMetadata AddLineageRequest array
gsp-dbt-lineage emit openmetadata \
    --lineage docs/examples/column_lineage.json \
    --out docs/examples/openmetadata_lineage.json

# 4. CI gate
gsp-dbt-lineage check \
    --lineage docs/examples/column_lineage.json \
    --min-node-coverage 0.95 --min-column-coverage 0.95

# 5. Baseline diff (degenerate self-diff just to exercise the command)
gsp-dbt-lineage diff \
    --current docs/examples/column_lineage.json \
    --baseline docs/examples/column_lineage.json
```

## What this proves and what it does not

**Proves**: the CLI is wired all the way through. `run`, `emit datahub`, `emit openmetadata`, `check`, `diff` each produce expected output against a real backend response.

**Does not prove**: that `gsp-dbt-lineage` outperforms sqlglot on every BigQuery / MSSQL construct. That claim is backed by the Phase 0.4 PoC dossier (10 wins / 11 active fixtures) in the companion ops repo, not by this single example.
