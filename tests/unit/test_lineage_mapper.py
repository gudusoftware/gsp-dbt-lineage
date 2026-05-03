from gsp_dbt_lineage.lineage_mapper import map_gsp_to_node


def _wrap(sqlflow: dict) -> dict:
    return {"code": 200, "data": {"sqlflow": sqlflow}}


def test_empty_response_yields_unsupported():
    out = map_gsp_to_node({"code": 200, "data": {"sqlflow": {}}}, node_id="m.x", dialect="dbvbigquery")
    assert out["status"] == "unsupported"
    assert out["upstream_tables"] == []
    assert out["columns"] == []


def test_single_relationship_resolves_table_and_column():
    response = _wrap({
        "dbobjs": {
            "servers": [{
                "name": "s",
                "databases": [{
                    "name": "d",
                    "schemas": [{
                        "name": "sch",
                        "tables": [
                            {"id": "1", "name": "src", "columns": [{"id": "11", "name": "id"}]},
                        ],
                        "others": [
                            {"id": "2", "name": "RS-1", "columns": [{"id": "21", "name": "id"}]},
                        ],
                    }],
                }],
            }],
        },
        "relationships": [{
            "id": "r1",
            "type": "fdd",
            "target": {"id": "21", "column": "id", "parentId": "2", "parentName": "RS-1"},
            "sources": [{"id": "11", "column": "id", "parentId": "1", "parentName": "src"}],
        }],
    })
    out = map_gsp_to_node(response, node_id="m.fct", dialect="dbvbigquery")
    assert out["status"] == "parsed"
    assert out["upstream_tables"] == ["s.d.sch.src"]
    assert len(out["columns"]) == 1
    col = out["columns"][0]
    assert col["name"] == "id"
    assert col["upstream"] == [{"table": "s.d.sch.src", "column": "id"}]


def test_default_server_db_stripped():
    response = _wrap({
        "dbobjs": {
            "servers": [{
                "name": "DEFAULT_SERVER",
                "databases": [{
                    "name": "DEFAULT",
                    "schemas": [{
                        "name": "myschema",
                        "tables": [
                            {"id": "1", "name": "users", "columns": [{"id": "11", "name": "uid"}]},
                        ],
                    }],
                }],
            }],
        },
        "relationships": [],
    })
    out = map_gsp_to_node(response, node_id="m.x", dialect="dbvbigquery")
    assert out["upstream_tables"] == ["myschema.users"]


def test_unknown_source_records_unresolved_no_fabricated_edge():
    response = _wrap({
        "dbobjs": {
            "servers": [{
                "name": "", "databases": [{
                    "name": "", "schemas": [{
                        "name": "",
                        "others": [{"id": "2", "name": "RS-1", "columns": [{"id": "21", "name": "id"}]}],
                    }],
                }],
            }],
        },
        "relationships": [{
            "id": "r1",
            "type": "fdd",
            "target": {"id": "21", "column": "id", "parentId": "2", "parentName": "RS-1"},
            "sources": [{"id": "11", "column": "id", "parentId": "999", "parentName": "<unknown>"}],
        }],
    })
    out = map_gsp_to_node(response, node_id="m.x", dialect="dbvbigquery")
    # The target was a known result-set, so a column entry exists but with no
    # upstream — the unknown source becomes an unresolved record. Never fabricate.
    assert out["columns"] == [] or all(not c["upstream"] for c in out["columns"])
    assert any(u["reason"] == "source_table_unknown" for u in out["unresolved"])


def test_synthetic_helper_columns_filtered():
    """COUNT, COUNT(N), and RELATIONROWS pseudo-columns must not pollute the
    column list — they're GSP-internal helpers (aggregate-call result-set
    column, row-count helper) emitted when an IF predicate contains
    `(SELECT COUNT(N) FROM ...)` or when a table participates in WHERE/ORDER BY.

    Repro of the dpriver/gsp-dbt-lineage E04b case (datahub-project/datahub#11654).
    """
    response = _wrap({
        "dbobjs": {
            "servers": [{
                "name": "", "databases": [{
                    "name": "", "schemas": [{
                        "name": "",
                        "tables": [
                            {"id": "1", "name": "src", "columns": [{"id": "11", "name": "id"}]},
                        ],
                        "others": [
                            {"id": "2", "name": "RS-1", "columns": [
                                {"id": "21", "name": "id"},
                                {"id": "22", "name": "COUNT"},
                                {"id": "23", "name": "COUNT(1)"},
                                {"id": "24", "name": "RELATIONROWS"},
                            ]},
                        ],
                    }],
                }],
            }],
        },
        "relationships": [
            {"type": "fdd",
             "target": {"column": "id", "parentId": "2"},
             "sources": [{"column": "id", "parentId": "1"}]},
            {"type": "fdd",
             "target": {"column": "COUNT", "parentId": "2"},
             "sources": [{"column": "id", "parentId": "1"}]},
            {"type": "fdd",
             "target": {"column": "COUNT(1)", "parentId": "2"},
             "sources": [{"column": "id", "parentId": "1"}]},
            {"type": "fdr",
             "target": {"column": "RELATIONROWS", "parentId": "2"},
             "sources": [{"column": "id", "parentId": "1"}]},
        ],
    })
    out = map_gsp_to_node(response, node_id="m.x", dialect="dbvbigquery")
    column_names = {c["name"] for c in out["columns"]}
    assert column_names == {"id"}, f"synthetic helpers leaked: {column_names}"


def test_procedural_evidence_emitted_for_multi_target_script():
    """A procedural script that writes to multiple TEMP TABLE / table targets
    must produce an evidence.procedural block listing each target with its
    per-column upstream edges. The flat columns list collapses same-named
    columns across write targets; the evidence block is the per-target receipt
    a reviewer needs to trust the result.
    """
    response = _wrap({
        "dbobjs": {
            "servers": [{
                "name": "", "databases": [{
                    "name": "", "schemas": [{
                        "name": "",
                        "tables": [
                            {"id": "1", "name": "src", "columns": [{"id": "11", "name": "id"}]},
                            {"id": "2", "name": "delta", "columns": [{"id": "21", "name": "id"}]},
                            {"id": "3", "name": "tmp1", "subType": "temp_table",
                             "columns": [{"id": "31", "name": "id"}]},
                            {"id": "4", "name": "tmp2", "subType": "temp_table",
                             "columns": [{"id": "41", "name": "id"}]},
                        ],
                        "others": [
                            {"id": "5", "name": "RS-1", "columns": [{"id": "51", "name": "id"}]},
                            {"id": "6", "name": "RS-2", "columns": [{"id": "61", "name": "id"}]},
                        ],
                    }],
                }],
            }],
        },
        "relationships": [
            {"type": "fdd", "target": {"column": "id", "parentId": "5"},
             "sources": [{"column": "id", "parentId": "1"}]},
            {"type": "fdd", "target": {"column": "id", "parentId": "3"},
             "sources": [{"column": "id", "parentId": "5"}]},
            {"type": "fdd", "target": {"column": "id", "parentId": "6"},
             "sources": [{"column": "id", "parentId": "2"}]},
            {"type": "fdd", "target": {"column": "id", "parentId": "4"},
             "sources": [{"column": "id", "parentId": "6"}]},
        ],
        "processes": [
            {"id": "p1", "type": "sstcreatetable", "name": "Create-1"},
            {"id": "p2", "type": "sstcreatetable", "name": "Create-2"},
        ],
    })
    out = map_gsp_to_node(response, node_id="m.x", dialect="dbvbigquery")
    proc = out["evidence"]["procedural"]
    assert proc["write_target_count"] == 2
    assert proc["column_edge_count"] == 2
    assert proc["process_count"] == 2
    target_tables = {wt["table"] for wt in proc["write_targets"]}
    assert target_tables == {"tmp1", "tmp2"}
    # Each write target must trace back to its real source through the RS hop.
    by_table = {wt["table"]: wt for wt in proc["write_targets"]}
    assert by_table["tmp1"]["from"] == ["src"]
    assert by_table["tmp2"]["from"] == ["delta"]


def test_no_evidence_block_for_single_target_ctas():
    """Single CREATE TABLE AS SELECT — no evidence.procedural needed; the flat
    columns list already says everything."""
    response = _wrap({
        "dbobjs": {
            "servers": [{
                "name": "", "databases": [{
                    "name": "", "schemas": [{
                        "name": "",
                        "tables": [
                            {"id": "1", "name": "src", "columns": [{"id": "11", "name": "id"}]},
                            {"id": "2", "name": "tgt", "columns": [{"id": "21", "name": "id"}]},
                        ],
                        "others": [{"id": "3", "name": "RS-1", "columns": [{"id": "31", "name": "id"}]}],
                    }],
                }],
            }],
        },
        "relationships": [
            {"type": "fdd", "target": {"column": "id", "parentId": "3"},
             "sources": [{"column": "id", "parentId": "1"}]},
            {"type": "fdd", "target": {"column": "id", "parentId": "2"},
             "sources": [{"column": "id", "parentId": "3"}]},
        ],
    })
    out = map_gsp_to_node(response, node_id="m.x", dialect="dbvbigquery")
    assert "evidence" not in out


def test_fdr_relation_classified_as_control():
    response = _wrap({
        "dbobjs": {
            "servers": [{
                "name": "", "databases": [{
                    "name": "", "schemas": [{
                        "name": "",
                        "tables": [
                            {"id": "1", "name": "src", "columns": [{"id": "11", "name": "id"}]},
                        ],
                        "others": [
                            {"id": "2", "name": "RS-1", "columns": [{"id": "21", "name": "x"}]},
                        ],
                    }],
                }],
            }],
        },
        "relationships": [{
            "id": "r1",
            "type": "fdr",
            "target": {"id": "21", "column": "x", "parentId": "2", "parentName": "RS-1"},
            "sources": [{"id": "11", "column": "id", "parentId": "1", "parentName": "src"}],
        }],
    })
    out = map_gsp_to_node(response, node_id="m.x", dialect="dbvbigquery")
    assert out["columns"][0]["transform"] == "control"
