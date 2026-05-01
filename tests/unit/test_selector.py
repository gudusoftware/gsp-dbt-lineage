from gsp_dbt_lineage.selector import select_nodes


def _nodes():
    return {
        "model.demo.stg_orders": {
            "name": "stg_orders",
            "resource_type": "model",
            "fqn": ["demo", "staging", "stg_orders"],
            "tags": ["staging"],
        },
        "model.demo.fct_orders": {
            "name": "fct_orders",
            "resource_type": "model",
            "fqn": ["demo", "marts", "fct_orders"],
            "tags": ["marts", "core"],
        },
        "model.demo.dim_users": {
            "name": "dim_users",
            "resource_type": "model",
            "fqn": ["demo", "marts", "dim_users"],
            "tags": ["marts"],
        },
        "test.demo.unique_stg_orders": {
            "name": "unique_stg_orders",
            "resource_type": "test",
            "fqn": ["demo", "tests", "unique_stg_orders"],
        },
    }


def _maps():
    parent = {
        "model.demo.fct_orders": ["model.demo.stg_orders"],
        "model.demo.dim_users": ["model.demo.stg_orders"],
    }
    child = {
        "model.demo.stg_orders": ["model.demo.fct_orders", "model.demo.dim_users"],
    }
    return parent, child


def test_select_all_when_no_token():
    nodes = _nodes()
    selected = select_nodes(nodes)
    assert set(selected) == set(nodes.keys())


def test_select_by_name():
    nodes = _nodes()
    assert select_nodes(nodes, select=["stg_orders"]) == ["model.demo.stg_orders"]


def test_select_by_tag():
    nodes = _nodes()
    assert set(select_nodes(nodes, select=["tag:marts"])) == {
        "model.demo.fct_orders",
        "model.demo.dim_users",
    }


def test_select_with_children():
    nodes = _nodes()
    parent, child = _maps()
    selected = select_nodes(nodes, parent, child, select=["stg_orders+"])
    assert set(selected) == {
        "model.demo.stg_orders",
        "model.demo.fct_orders",
        "model.demo.dim_users",
    }


def test_select_with_parents():
    nodes = _nodes()
    parent, child = _maps()
    selected = select_nodes(nodes, parent, child, select=["+fct_orders"])
    assert set(selected) == {"model.demo.fct_orders", "model.demo.stg_orders"}


def test_exclude_removes_match():
    nodes = _nodes()
    selected = select_nodes(nodes, select=["tag:marts"], exclude=["dim_users"])
    assert selected == ["model.demo.fct_orders"]


def test_resource_type_filter():
    nodes = _nodes()
    selected = select_nodes(nodes, resource_types=["model"])
    assert "test.demo.unique_stg_orders" not in selected
    assert "model.demo.stg_orders" in selected
