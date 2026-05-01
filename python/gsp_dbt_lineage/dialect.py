"""Map dbt adapter types to GSP dbvendor identifiers.

ADR-007 locks this as a static dict. Plugin/entry-point extensibility deferred.
The CLI accepts `--dialect` to override per-run, which is the documented
escape hatch for unsupported adapters.
"""

from __future__ import annotations

# dbt adapter type (as recorded in manifest metadata.adapter_type) -> GSP dbvendor.
# GSP's `EDbVendor.fromAlias` accepts the short name (no `dbv` prefix) when
# called via the JAR CLI; the HTTP API accepts both forms but prefers the long
# form. Stored canonically as the long form; backend.py downconverts as needed.
ADAPTER_TO_DBVENDOR: dict[str, str] = {
    "bigquery": "dbvbigquery",
    "snowflake": "dbvsnowflake",
    "databricks": "dbvdatabricks",
    "spark": "dbvsparksql",
    "sqlserver": "dbvmssql",
    "synapse": "dbvmssql",
    "fabric": "dbvmssql",
    "postgres": "dbvpostgresql",
    "redshift": "dbvredshift",
    "trino": "dbvtrino",
    "duckdb": "dbvduckdb",
    "clickhouse": "dbvclickhouse",
    "mysql": "dbvmysql",
    "oracle": "dbvoracle",
    "athena": "dbvathena",
    "doris": "dbvdoris",
    "vertica": "dbvvertica",
    "teradata": "dbvteradata",
    "db2": "dbvdb2",
}


class UnknownAdapterError(Exception):
    """Raised when neither --dialect nor adapter_type produces a known dbvendor."""


def resolve_dialect(adapter_type: str | None, override: str | None = None) -> str:
    """Resolve the GSP dbvendor for a model.

    Priority: explicit `override` (CLI --dialect) > manifest adapter_type > error.

    `override` may be either the short alias ("bigquery") or the full vendor
    ("dbvbigquery") — both normalize to the long form.
    """
    if override:
        return _canon(override)
    if adapter_type:
        key = adapter_type.strip().lower()
        if key in ADAPTER_TO_DBVENDOR:
            return ADAPTER_TO_DBVENDOR[key]
    raise UnknownAdapterError(
        f"unknown adapter_type {adapter_type!r}; pass --dialect to override. "
        f"Known: {sorted(ADAPTER_TO_DBVENDOR)}"
    )


def _canon(s: str) -> str:
    s = s.strip().lower()
    if s.startswith("dbv"):
        return s
    if s in ADAPTER_TO_DBVENDOR:
        return ADAPTER_TO_DBVENDOR[s]
    return f"dbv{s}"
