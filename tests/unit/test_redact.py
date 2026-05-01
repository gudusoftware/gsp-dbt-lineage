from gsp_dbt_lineage.redact import redact


def test_string_literals_replaced():
    assert "<REDACTED>" in redact("SELECT 'secret' FROM x")


def test_numeric_literals_replaced():
    assert redact("SELECT 42 FROM x").endswith("FROM x")
    assert "0" in redact("SELECT 42 FROM x")


def test_quoted_identifiers_preserved():
    out = redact("SELECT `secret_col` FROM `proj.ds.t`")
    assert "secret_col" in out
    assert "proj.ds.t" in out


def test_double_quoted_idents_preserved():
    out = redact('SELECT "secret" FROM "tbl"')
    assert '"secret"' in out


def test_bracketed_idents_preserved():
    out = redact("SELECT [secret] FROM [tbl]")
    assert "[secret]" in out


def test_keywords_preserved():
    out = redact("SELECT 'a', 1 FROM x WHERE y = 'b' AND z > 99")
    assert "SELECT" in out
    assert "FROM" in out
    assert "WHERE" in out
    assert "AND" in out
    assert "<REDACTED>" in out
