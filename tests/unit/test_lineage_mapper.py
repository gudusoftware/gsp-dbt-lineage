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


def test_orphan_column_diagnostic_attached_to_unresolved_column():
    """A GSP `errors` block with `find orphan column(10500) near: [X](r,c)` must
    surface as both an `evidence.parser_diagnostics` entry and a node-level
    `unresolved` entry tagged with `parser_orphan_column`. Repro of the E23b
    case (sqlglot#4338) where 7 unqualified projection columns are flagged.
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
                        "views": [
                            {"id": "9", "name": "v_target", "columns": [
                                {"id": "91", "name": "id"},
                                {"id": "92", "name": "TARGET_DIVISION_SORT"},
                            ]},
                        ],
                        "others": [
                            {"id": "2", "name": "RS-1", "columns": [
                                {"id": "21", "name": "id"},
                                {"id": "22", "name": "TARGET_DIVISION_SORT"},
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
             "target": {"column": "id", "parentId": "9"},
             "sources": [{"column": "id", "parentId": "2"}]},
            # Target_Division_Sort has a target entry but its only source sits
            # on an unknown parent — matches GSP's "orphan column" symptom.
            {"type": "fdd",
             "target": {"column": "TARGET_DIVISION_SORT", "parentId": "2"},
             "sources": [{"column": "TARGET_DIVISION_SORT", "parentId": "999"}]},
        ],
        "errors": [{
            "errorType": "SyntaxHint",
            "errorMessage": "find orphan column(10500) near: [Target_Division_Sort](14,8)",
            "originCoordinates": [{"x": 14, "y": 8}, {"x": 14, "y": 30}],
        }],
    })
    out = map_gsp_to_node(response, node_id="m.x", dialect="dbvmssql")

    diags = out["evidence"]["parser_diagnostics"]
    assert len(diags) == 1
    assert diags[0]["category"] == "orphan_column"
    assert diags[0]["near_column"] == "Target_Division_Sort"
    assert diags[0]["line"] == 14
    assert diags[0]["col"] == 8
    assert diags[0]["type"] == "SyntaxHint"

    # Node-level unresolved must carry the per-column attribution so a reader
    # can answer "why is this column low confidence?" without cross-referencing
    # the parser diagnostics block.
    orphan = [u for u in out["unresolved"] if u["reason"] == "parser_orphan_column"]
    assert len(orphan) == 1
    assert orphan[0]["target_column"] == "TARGET_DIVISION_SORT"
    assert orphan[0]["line"] == 14
    assert orphan[0]["col"] == 8
    assert "orphan column" in orphan[0]["parser_message"].lower()
    # `near` is intentionally absent — `target_column` already names the
    # affected projection; the GSP-side spelling is preserved on the
    # diagnostic itself (evidence.parser_diagnostics[*].near_column).
    assert "near" not in orphan[0]


def test_columns_without_upstream_get_upstream_unresolved_entry():
    """Columns the mapper could not trace (no orphan-column hint, no upstream
    found) must still be honestly recorded as `upstream_unresolved` so the
    document explains itself without manual reading of the GSP response.
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
                                {"id": "22", "name": "case_when_derived"},
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
            # case_when_derived has a target entry but its sources are all on
            # an unknown parent — mapper must record the column with no
            # upstream rather than silently drop it.
            {"type": "fdd",
             "target": {"column": "case_when_derived", "parentId": "2"},
             "sources": [{"column": "x", "parentId": "999"}]},
        ],
    })
    out = map_gsp_to_node(response, node_id="m.x", dialect="dbvbigquery")

    by_name = {c["name"]: c for c in out["columns"]}
    assert by_name["case_when_derived"]["upstream"] == []
    assert by_name["case_when_derived"]["confidence"] == "low"

    reasons = {(u["reason"], u.get("target_column")) for u in out["unresolved"]}
    assert ("upstream_unresolved", "case_when_derived") in reasons
    # The unknown-source record from the relationship walk is preserved too.
    assert any(u["reason"] == "source_table_unknown" for u in out["unresolved"])

    # No parser diagnostics block when the GSP response had no errors.
    assert "parser_diagnostics" not in out.get("evidence", {})


def test_malformed_errors_block_does_not_crash_mapper():
    """GSP cloud / local-jar shapes have drifted historically. The mapper
    must tolerate non-list `errors`, non-dict entries, dict-typed
    `originCoordinates`, and non-string fields without raising. Regression
    guard against codex review P1 finding."""
    response = _wrap({
        "dbobjs": {"servers": [{"name": "", "databases": [{"name": "", "schemas": [{
            "name": "",
            "tables": [{"id": "1", "name": "src", "columns": [{"id": "11", "name": "id"}]}],
            "others": [{"id": "2", "name": "RS-1", "columns": [{"id": "21", "name": "id"}]}],
        }]}]}]},
        "relationships": [{"type": "fdd",
                           "target": {"column": "id", "parentId": "2"},
                           "sources": [{"column": "id", "parentId": "1"}]}],
        # Each of these would crash an unhardened extractor.
        "errors": [
            "not a dict",
            None,
            {"errorMessage": None, "errorType": "Hint"},
            {"errorMessage": 42},
            {"errorMessage": "find orphan column(10500) near: [X](2,1)",
             "originCoordinates": {"x": 2, "y": 1}},  # dict instead of list
            {"errorMessage": "warning",
             "originCoordinates": [{}]},  # list of empty dicts
        ],
    })
    out = map_gsp_to_node(response, node_id="m.x", dialect="dbvmssql")
    diags = out["evidence"]["parser_diagnostics"]
    # Only the two well-formed entries should survive.
    assert len(diags) == 2
    assert any(d.get("category") == "orphan_column" for d in diags)


def test_orphan_match_prefers_exact_over_uppercase_fallback():
    """Case-sensitive quoted identifiers (`"MyCol"` distinct from `"mycol"`)
    must bind to the diagnostic that names them exactly, not collapse onto a
    same-spelling neighbor via uppercase normalization."""
    response = _wrap({
        "dbobjs": {"servers": [{"name": "", "databases": [{"name": "", "schemas": [{
            "name": "",
            "tables": [{"id": "1", "name": "src", "columns": [{"id": "11", "name": "x"}]}],
            "others": [{"id": "2", "name": "RS-1", "columns": [
                {"id": "21", "name": "MyCol"},
            ]}],
        }]}]}]},
        "relationships": [{"type": "fdd",
                           "target": {"column": "MyCol", "parentId": "2"},
                           "sources": [{"column": "x", "parentId": "999"}]}],
        "errors": [{
            "errorType": "SyntaxHint",
            "errorMessage": "find orphan column(10500) near: [MyCol](3,5)",
            "originCoordinates": [{"x": 3, "y": 5}],
        }],
    })
    out = map_gsp_to_node(response, node_id="m.x", dialect="dbvbigquery")
    orphan = [u for u in out["unresolved"] if u["reason"] == "parser_orphan_column"]
    assert len(orphan) == 1
    assert orphan[0]["target_column"] == "MyCol"
    assert orphan[0]["parser_message"].endswith("[MyCol](3,5)")


def test_non_orphan_parser_hint_recorded_as_node_level_warning():
    """Non-orphan-column parser hints (generic SyntaxHint) attach to the node-
    level unresolved array as `parser_syntax_hint` so they are not lost."""
    response = _wrap({
        "dbobjs": {"servers": [{"name": "", "databases": [{"name": "", "schemas": [{
            "name": "",
            "tables": [{"id": "1", "name": "src", "columns": [{"id": "11", "name": "id"}]}],
            "others": [{"id": "2", "name": "RS-1", "columns": [{"id": "21", "name": "id"}]}],
        }]}]}]},
        "relationships": [{"type": "fdd",
                           "target": {"column": "id", "parentId": "2"},
                           "sources": [{"column": "id", "parentId": "1"}]}],
        "errors": [{
            "errorType": "SyntaxHint",
            "errorMessage": "expected statement separator near token 'GO'",
            "originCoordinates": [{"x": 3, "y": 1}],
        }],
    })
    out = map_gsp_to_node(response, node_id="m.x", dialect="dbvmssql")
    hint = [u for u in out["unresolved"] if u["reason"] == "parser_syntax_hint"]
    assert len(hint) == 1
    assert "GO" in hint[0]["parser_message"]
    assert hint[0]["line"] == 3
    assert hint[0]["col"] == 1


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
