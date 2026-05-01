# CI integration

`gsp-dbt-lineage` ships a CI-friendly `check` command and a GitHub Action wrapper.

## GitHub Actions (drop-in)

```yaml
# .github/workflows/lineage.yml
name: Column lineage check
on:
  pull_request: { branches: [main] }

jobs:
  lineage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: dbt build
        run: |
          pip install dbt-bigquery
          dbt build
      - uses: gudusoftware/dbt-lineage@v0.0.1
        with:
          backend: authenticated
          user-id: ${{ secrets.GSP_USER_ID }}
          secret-key: ${{ secrets.GSP_SECRET_KEY }}
          min-node-coverage: '0.95'
          fail-on-regression: 'true'
          baseline: target/gudu/column_lineage.prev.json   # optional
```

## Manual check (any CI)

```bash
pip install gsp-dbt-lineage
dbt build
gsp-dbt-lineage run \
    --manifest target/manifest.json \
    --backend authenticated --user-id "$GSP_USER_ID" --secret-key "$GSP_SECRET_KEY" \
    --out target/gudu/column_lineage.json
gsp-dbt-lineage check \
    --lineage target/gudu/column_lineage.json \
    --min-node-coverage 0.95 \
    --fail-on-regression --baseline path/to/baseline.json
```

## Exit codes

| Exit | Meaning |
|---|---|
| `0` | All gates passed |
| `2` | CLI usage error |
| `10` | Lineage doc unreadable |
| `12` | A `check` gate failed (coverage / regression / unsupported / failed) |
| `99` | Unexpected error |

`check` exits non-zero on:

| Gate | Default | Override |
|---|---|---|
| `--min-node-coverage` | not set | `--min-node-coverage 0.95` |
| `--min-column-coverage` | not set | `--min-column-coverage 0.80` |
| `--fail-on-unsupported` | off | `--fail-on-unsupported` |
| `--fail-on-failed` | **on in CI** (auto-detected) | `--fail-on-failed` to force |
| `--fail-on-regression` | off | `--fail-on-regression --baseline=PATH` |

## Anonymous-tier guard

When run in CI (any `CI=true` family of env vars set) with `--backend anonymous`, the CLI refuses if your selection has more than 50 eligible nodes — the 50/day per-IP quota would burn out within a single run. Switch to authenticated, self-hosted, or local-JAR.

## dbt Cloud

dbt Cloud's hosted runtime cannot exec the CLI directly (per ADR-007). Pattern:

1. Run `dbt build` in dbt Cloud.
2. Download `manifest.json` via the dbt Cloud API in your CI.
3. Run `gsp-dbt-lineage run --manifest /path/to/downloaded/manifest.json ...` in your CI.
4. Commit / publish the `column_lineage.json` artifact + DataHub MCPs.

## Caching

The CLI caches GSP responses by SQL hash under `.gsp-cache/`. Hit-rate >50% on second runs of the same project is typical. Bust the cache by upgrading the CLI (cache key includes `cli_version`).
