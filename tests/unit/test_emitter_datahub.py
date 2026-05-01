from gsp_dbt_lineage.emitters import datahub as dh


def test_dialect_to_platform_known():
    assert dh.dialect_to_platform("dbvbigquery") == "bigquery"
    assert dh.dialect_to_platform("dbvmssql") == "mssql"


def test_dialect_to_platform_unknown_strips_dbv():
    assert dh.dialect_to_platform("dbvfoobar") == "foobar"


def test_emit_skips_skipped_status():
    doc = {"nodes": [{
        "node_id": "model.x.skip",
        "status": "skipped",
        "dialect": "dbvbigquery",
        "upstream_tables": [],
        "columns": [],
    }]}
    assert dh.emit(doc) == []


def test_emit_produces_one_mcp_per_parsed_node():
    doc = {"nodes": [{
        "node_id": "model.x.fct",
        "status": "parsed",
        "dialect": "dbvbigquery",
        "upstream_tables": ["src.t"],
        "columns": [{
            "name": "id",
            "upstream": [{"table": "src.t", "column": "id"}],
            "transform": "direct",
        }],
    }]}
    mcps = dh.emit(doc)
    assert len(mcps) == 1
    mcp = mcps[0]
    assert mcp["entityType"] == "dataset"
    assert "bigquery" in mcp["entityUrn"]
    aspect = mcp["aspect"]["json"]
    assert len(aspect["upstreams"]) == 1
    assert len(aspect["fineGrainedLineages"]) == 1
    fgl = aspect["fineGrainedLineages"][0]
    assert "src.t" in fgl["upstreams"][0]
    assert fgl["transformOperation"] == "direct"


def test_emit_handles_partial_status():
    doc = {"nodes": [{
        "node_id": "model.x.partial",
        "status": "partial",
        "dialect": "dbvmssql",
        "upstream_tables": ["t"],
        "columns": [{"name": "x", "upstream": []}],
    }]}
    mcps = dh.emit(doc)
    assert len(mcps) == 1


def test_platform_map_override():
    doc = {"nodes": [{
        "node_id": "x",
        "status": "parsed",
        "dialect": "dbvbigquery",
        "upstream_tables": [],
        "columns": [],
    }]}
    mcps = dh.emit(doc, platform_map={"dbvbigquery": "bq-custom"})
    assert "bq-custom" in mcps[0]["entityUrn"]
