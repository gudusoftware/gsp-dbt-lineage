from gsp_dbt_lineage.cache import FileCache, cache_key, normalize_sql


def test_normalize_collapses_whitespace():
    assert normalize_sql("  SELECT\n\t1\n  FROM\nx ") == "SELECT 1 FROM x"


def test_normalize_preserves_string_literal_with_comment_chars():
    # If we naively stripped comments, the literal would lose '-- world',
    # silently colliding with `SELECT 'hello '` in the cache.
    s = "SELECT 'hello -- world' FROM x"
    assert normalize_sql(s) == "SELECT 'hello -- world' FROM x"


def test_normalize_preserves_string_literal_with_block_comment_chars():
    s = "SELECT '/* not a comment */' FROM x"
    assert normalize_sql(s) == "SELECT '/* not a comment */' FROM x"


def test_cache_key_is_stable_across_whitespace_diffs():
    a = cache_key("SELECT 1\nFROM x", "dbvbigquery", "anonymous", "v1", "0.0.1")
    b = cache_key("SELECT  1\nFROM x", "dbvbigquery", "anonymous", "v1", "0.0.1")
    assert a == b


def test_cache_key_differs_when_comments_differ():
    # Comment-stripping would corrupt literals (see test above); cost of
    # safety is that comment-only diffs miss cache. Document the expected behavior.
    a = cache_key("SELECT 1 -- v1", "dbvbigquery", "anonymous", "v1", "0.0.1")
    b = cache_key("SELECT 1 -- v2", "dbvbigquery", "anonymous", "v1", "0.0.1")
    assert a != b


def test_cache_key_differs_on_dialect():
    a = cache_key("SELECT 1", "dbvbigquery", "anonymous", "v1", "0.0.1")
    b = cache_key("SELECT 1", "dbvmssql", "anonymous", "v1", "0.0.1")
    assert a != b


def test_cache_key_differs_on_cli_version():
    a = cache_key("SELECT 1", "dbvbigquery", "anonymous", "v1", "0.0.1")
    b = cache_key("SELECT 1", "dbvbigquery", "anonymous", "v1", "0.0.2")
    assert a != b


def test_filecache_round_trip(tmp_path):
    c = FileCache(tmp_path / "cache")
    key = "deadbeef" + "0" * 56
    assert c.get(key) is None
    c.put(key, {"code": 200, "data": {"x": 1}})
    assert c.get(key) == {"code": 200, "data": {"x": 1}}


def test_filecache_stats(tmp_path):
    c = FileCache(tmp_path / "cache")
    c.get("missing-1" + "0" * 56)
    c.get("missing-2" + "0" * 56)
    c.put("hit" + "0" * 61, {"x": 1})
    c.get("hit" + "0" * 61)
    stats = c.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 2
