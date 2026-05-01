from gsp_dbt_lineage.emitters import openmetadata as om


def test_skips_skipped_status():
    doc = {"nodes": [{
        "node_id": "model.x.skip", "status": "skipped",
        "dialect": "dbvbigquery", "upstream_tables": [], "columns": [],
    }]}
    assert om.emit(doc) == []


def test_emits_one_request_per_upstream():
    doc = {"nodes": [{
        "node_id": "model.x.fct",
        "status": "parsed",
        "dialect": "dbvbigquery",
        "upstream_tables": ["src.t1", "src.t2"],
        "columns": [
            {"name": "id", "upstream": [{"table": "src.t1", "column": "id"}]},
            {"name": "amt", "upstream": [{"table": "src.t2", "column": "amount"}]},
        ],
    }]}
    reqs = om.emit(doc)
    assert len(reqs) == 2
    # Each request is a distinct edge — OM resolves fullyQualifiedName -> UUID at ingest
    assert {r["edge"]["fromEntity"]["fullyQualifiedName"] for r in reqs} == {
        "bigquery.src.t1", "bigquery.src.t2",
    }
    # The 'id' (UUID) field must NOT be set — we don't have UUIDs at file-emit time.
    for r in reqs:
        assert "id" not in r["edge"]["fromEntity"]
        assert "id" not in r["edge"]["toEntity"]


def test_column_lineage_filters_by_upstream_table():
    doc = {"nodes": [{
        "node_id": "model.x.fct",
        "status": "parsed",
        "dialect": "dbvbigquery",
        "upstream_tables": ["src.t1", "src.t2"],
        "columns": [
            {"name": "id", "upstream": [{"table": "src.t1", "column": "id"}]},
            {"name": "amt", "upstream": [{"table": "src.t2", "column": "amount"}]},
        ],
    }]}
    reqs = om.emit(doc)
    by_upstream = {r["edge"]["fromEntity"]["fullyQualifiedName"]: r for r in reqs}
    cl1 = by_upstream["bigquery.src.t1"]["edge"]["lineageDetails"]["columnsLineage"]
    cl2 = by_upstream["bigquery.src.t2"]["edge"]["lineageDetails"]["columnsLineage"]
    # t1 column-lineage must only reference t1 columns, not t2.
    assert all("src.t1" in c["fromColumns"][0] for c in cl1)
    assert all("src.t2" in c["fromColumns"][0] for c in cl2)


def test_service_name_override():
    doc = {"nodes": [{
        "node_id": "model.x.fct", "status": "parsed",
        "dialect": "dbvbigquery", "upstream_tables": ["src.t"],
        "columns": [{"name": "id", "upstream": [{"table": "src.t", "column": "id"}]}],
    }]}
    reqs = om.emit(doc, service_name="custom-svc")
    assert reqs[0]["edge"]["fromEntity"]["fullyQualifiedName"].startswith("custom-svc.")
    assert reqs[0]["edge"]["toEntity"]["fullyQualifiedName"].startswith("custom-svc.")
