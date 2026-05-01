# Backend modes

`gsp-dbt-lineage` supports four dispatch modes for the underlying GSP/SQLFlow parser. Choose based on volume, where SQL can travel, and your enterprise data-handling rules.

## 1. `--backend anonymous`

```bash
gsp-dbt-lineage run --backend anonymous --manifest target/manifest.json
```

- **Volume:** 50 calls/day per IP.
- **Where SQL goes:** `https://api.gudusoft.com/gspLive_backend/api/anonymous/lineage`.
- **Auth:** none.
- **Use when:** evaluating the package on a tiny project (<50 models) once.
- **CI:** the CLI will refuse anonymous mode in CI environments above 50 nodes (per R2 of the runbook). Switch to authenticated or self-hosted.

## 2. `--backend authenticated`

```bash
gsp-dbt-lineage run \
    --backend authenticated \
    --user-id "$GSP_USER_ID" --secret-key "$GSP_SECRET_KEY"
```

- **Volume:** 10,000/month free; 100,000/day on Pro tier ($50/mo); unlimited on Enterprise.
- **Where SQL goes:** `https://api.gudusoft.com/gspLive_backend/...` over HTTPS.
- **Auth:** two-step token exchange (POST `secretKey` -> JWT, then send token).
- **Use when:** standard production CI; SQL can leave your VPC.

## 3. `--backend self_hosted`

```bash
gsp-dbt-lineage run \
    --backend self_hosted \
    --url http://your-host:8165/gspLive_backend/sqlflow/generation/sqlflow/exportFullLineageAsJson \
    --user-id "$GSP_USER_ID" --secret-key "$GSP_SECRET_KEY"
```

- **Volume:** unlimited (within your container's resource budget).
- **Where SQL goes:** your own Docker container running `gudusoft/gsp-service`.
- **Auth:** same two-step token exchange as authenticated, but against your endpoint.
- **Use when:** SQL must NOT leave your VPC; air-gapped or compliance-restricted environments.
- **No default URL** — the URL must be supplied; deployments vary.

## 4. `--backend local_jar`

```bash
gsp-dbt-lineage run \
    --backend local_jar \
    --jar-path /opt/gsp-shaded.jar
```

- **Volume:** unlimited; no network at all.
- **Where SQL goes:** stays in-process. JVM subprocess shells out to `gudusoft.gsqlparser.dlineage.DataFlowAnalyzer`.
- **Auth:** none (you bought a license to ship the JAR).
- **Use when:** strictest air-gap; SQL never touches a network socket.
- **Trade-off:** ~0.5–1s JVM cold-start per call. For large projects, prefer self-hosted.
- **JAR not bundled** — purchase / license separately from Gudu Software.

## Picking a mode

| Constraint | Pick |
|---|---|
| Just trying it | `anonymous` (one-shot eval) |
| Daily CI on <100 models | `authenticated` |
| Daily CI on >100 models, fast | `authenticated` (Pro tier) |
| SQL cannot leave VPC | `self_hosted` |
| No network egress at all | `local_jar` |

## Caching across modes

The cache key includes `backend_mode`, so cache entries are not shared across modes — switching from `authenticated` to `self_hosted` is a cold cache. Within a single mode the hit-rate is typically >50% on second runs of the same project.
