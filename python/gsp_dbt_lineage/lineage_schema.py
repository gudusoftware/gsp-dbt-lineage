"""JSON schema for column_lineage.json (schema_version 0.2.x).

Pinned for the v1 lifetime per ADR-007 / runbook §4.5. Defensive readers must
accept any future minor that adds fields, so the schema uses
`additionalProperties: true` at every level.
"""

from __future__ import annotations

from typing import Any

import jsonschema

SCHEMA_VERSION = "0.2.x"

LINEAGE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://sqlparser.com/dbt-lineage/schemas/column_lineage-0.2.json",
    "title": "gsp-dbt-lineage column_lineage.json",
    "type": "object",
    "additionalProperties": True,
    "required": ["schema_version", "generator", "manifest_metadata", "backend", "stats", "nodes"],
    "properties": {
        "schema_version": {"type": "string"},
        "generator": {"type": "string"},
        "generated_at": {"type": "string"},
        "manifest_metadata": {
            "type": "object",
            "additionalProperties": True,
            "required": ["dbt_version", "project_name", "selected_count", "eligible_count"],
            "properties": {
                "dbt_version": {"type": "string"},
                "dbt_schema_version": {"type": "string"},
                "project_name": {"type": "string"},
                "adapter_type": {"type": ["string", "null"]},
                "selected_count": {"type": "integer", "minimum": 0},
                "eligible_count": {"type": "integer", "minimum": 0},
            },
        },
        "backend": {
            "type": "object",
            "additionalProperties": True,
            "required": ["mode"],
            "properties": {
                "mode": {"type": "string"},
                "parser_version": {"type": "string"},
                "cli_version": {"type": "string"},
            },
        },
        "stats": {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "parsed": {"type": "integer", "minimum": 0},
                "partial": {"type": "integer", "minimum": 0},
                "unsupported": {"type": "integer", "minimum": 0},
                "failed": {"type": "integer", "minimum": 0},
                "skipped": {"type": "integer", "minimum": 0},
                "total_columns": {"type": "integer", "minimum": 0},
                "resolved_columns": {"type": "integer", "minimum": 0},
                "coverage": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
        "nodes": {
            "type": "array",
            "items": {"$ref": "#/$defs/node"},
        },
    },
    "$defs": {
        "node": {
            "type": "object",
            "additionalProperties": True,
            "required": ["node_id", "status"],
            "properties": {
                "node_id": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["parsed", "partial", "unsupported", "failed", "skipped"],
                },
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                "dialect": {"type": ["string", "null"]},
                "upstream_tables": {"type": "array", "items": {"type": "string"}},
                "downstream": {"type": "array", "items": {"type": "string"}},
                "columns": {"type": "array", "items": {"$ref": "#/$defs/column"}},
                "unresolved": {"type": "array", "items": {"type": "object"}},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
        },
        "column": {
            "type": "object",
            "additionalProperties": True,
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "upstream": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": True,
                        "required": ["table", "column"],
                        "properties": {
                            "table": {"type": "string"},
                            "column": {"type": "string"},
                        },
                    },
                },
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                "transform": {
                    "type": "string",
                    "enum": ["direct", "expression", "control", "aggregate", "unknown"],
                },
            },
        },
    },
}


class SchemaError(Exception):
    """Raised when an emitted lineage doc fails schema validation."""


def validate_lineage(doc: dict[str, Any]) -> None:
    """Validate a column_lineage.json document.

    Raises SchemaError with a useful message on failure.
    """
    try:
        jsonschema.validate(doc, LINEAGE_SCHEMA)
    except jsonschema.ValidationError as e:
        path = ".".join(str(p) for p in e.absolute_path)
        raise SchemaError(f"validation failed at $.{path}: {e.message}") from e
