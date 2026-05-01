import pytest

from gsp_dbt_lineage.dialect import (
    ADAPTER_TO_DBVENDOR,
    UnknownAdapterError,
    resolve_dialect,
)


@pytest.mark.parametrize("adapter,expected", list(ADAPTER_TO_DBVENDOR.items()))
def test_known_adapters(adapter, expected):
    assert resolve_dialect(adapter) == expected


def test_override_short_alias():
    assert resolve_dialect("postgres", override="bigquery") == "dbvbigquery"


def test_override_long_alias():
    assert resolve_dialect("postgres", override="dbvbigquery") == "dbvbigquery"


def test_override_normalizes_whitespace_and_case():
    assert resolve_dialect(None, override="  BigQuery ") == "dbvbigquery"


def test_unknown_adapter_raises():
    with pytest.raises(UnknownAdapterError):
        resolve_dialect("totally-fake-adapter")


def test_synapse_and_fabric_map_to_mssql():
    assert resolve_dialect("synapse") == "dbvmssql"
    assert resolve_dialect("fabric") == "dbvmssql"


def test_override_with_unknown_alias_falls_through_to_dbv_prefix():
    # An unknown short alias is wrapped as dbv<alias>; the backend will reject
    # if the vendor isn't recognized, but we want resolve_dialect to be
    # permissive here so users can pass forward-looking names.
    assert resolve_dialect(None, override="someNewVendor") == "dbvsomenewvendor"
