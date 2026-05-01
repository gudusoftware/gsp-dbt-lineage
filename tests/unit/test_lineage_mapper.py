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
