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


def test_sql_doubled_quote_escape_treated_as_one_literal():
    # `'O''Brien'` is one literal in SQL standard. The redactor must NOT split
    # it into two literals (which would surface ' Brien' as if it were SQL.)
    out = redact("SELECT 'O''Brien' FROM x WHERE y = 'z'")
    # The output should have exactly two REDACTED markers (one per literal).
    assert out.count("<REDACTED>") == 2
    # And no orphan apostrophes.
    assert "Brien" not in out


def test_keywords_preserved():
    out = redact("SELECT 'a', 1 FROM x WHERE y = 'b' AND z > 99")
    assert "SELECT" in out
    assert "FROM" in out
    assert "WHERE" in out
    assert "AND" in out
    assert "<REDACTED>" in out
