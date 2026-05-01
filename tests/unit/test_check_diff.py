"""Tests for `check` and `diff` commands."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gsp_dbt_lineage.cli import _diff_regressions


def _doc(eligible=10, parsed=8, partial=1, failed=1, total_columns=20, resolved_columns=18, nodes=None):
    return {
        "manifest_metadata": {"selected_count": eligible, "eligible_count": eligible},
        "stats": {
            "parsed": parsed, "partial": partial, "failed": failed, "skipped": 0,
            "total_columns": total_columns, "resolved_columns": resolved_columns,
            "coverage": resolved_columns / total_columns if total_columns else 0,
        },
        "nodes": nodes or [],
    }


def test_diff_no_regression_returns_empty():
    a = _doc(nodes=[{"node_id": "x", "columns": [{"upstream": [{"table": "t", "column": "c"}]}]}])
    b = _doc(nodes=[{"node_id": "x", "columns": [{"upstream": [{"table": "t", "column": "c"}]}]}])
    assert _diff_regressions(current=a, baseline=b) == []


def test_diff_detects_lost_edges():
    a = _doc(nodes=[{"node_id": "x", "columns": [{"upstream": []}]}])
    b = _doc(nodes=[{"node_id": "x", "columns": [{"upstream": [{"table": "t", "column": "c"}]}]}])
    regs = _diff_regressions(current=a, baseline=b)
    assert len(regs) == 1
    assert regs[0]["node_id"] == "x"
    assert regs[0]["edges_lost"] == 1


def test_diff_ignores_new_nodes():
    a = _doc(nodes=[
        {"node_id": "x", "columns": [{"upstream": [{"table": "t", "column": "c"}]}]},
        {"node_id": "y", "columns": [{"upstream": [{"table": "t", "column": "c"}]}]},
    ])
    b = _doc(nodes=[
        {"node_id": "x", "columns": [{"upstream": [{"table": "t", "column": "c"}]}]},
    ])
    # y is new (no baseline), no regression
    assert _diff_regressions(current=a, baseline=b) == []


def test_diff_ignores_deleted_nodes():
    a = _doc(nodes=[
        {"node_id": "x", "columns": [{"upstream": [{"table": "t", "column": "c"}]}]},
    ])
    b = _doc(nodes=[
        {"node_id": "x", "columns": [{"upstream": [{"table": "t", "column": "c"}]}]},
        {"node_id": "y", "columns": [{"upstream": [{"table": "t", "column": "c"}]}]},
    ])
    # y was removed; not a "regression" (the node is gone, can't lose lineage on it)
    assert _diff_regressions(current=a, baseline=b) == []
