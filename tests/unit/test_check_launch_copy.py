import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
import check_launch_copy as linter  # noqa: E402


def test_find_cited_rows_only_returns_known_ids():
    text = "We cite E03 and E07. Also E99 is an external code."
    known = {"E03", "E04", "E07"}
    assert linter.find_cited_rows(text, known) == ["E03", "E07"]


def test_find_cited_rows_dedupes():
    text = "E03 once, E03 twice, E03 thrice."
    assert linter.find_cited_rows(text, {"E03", "E04"}) == ["E03"]


def test_find_cited_rows_word_boundary():
    # E033 should not match — it's not E03.
    text = "E033 is bigger than E03."
    assert linter.find_cited_rows(text, {"E03"}) == ["E03"]


def test_lint_passes_active_rows():
    by_id = {"E03": "active", "E07": "regression"}
    passing, failing = linter.lint("see E03 for details", by_id)
    assert len(passing) == 1
    assert not failing


def test_lint_fails_regression_row():
    by_id = {"E03": "active", "E07": "regression"}
    passing, failing = linter.lint("we leverage E07 capability", by_id)
    assert len(failing) == 1
    assert "E07" in failing[0]
    assert not passing


def test_lint_fails_unverified_row():
    by_id = {"E03": "unverified"}
    passing, failing = linter.lint("E03 will save you", by_id)
    assert failing


def test_lint_passes_framework_active_and_manual_active():
    by_id = {"E05": "framework-active", "E01": "manual-active"}
    passing, failing = linter.lint("Cited: E01, E05.", by_id)
    assert len(passing) == 2
    assert not failing


def test_lint_ignores_unknown_external_codes():
    # E99 isn't in the index — should not appear as failure or passing.
    by_id = {"E03": "active"}
    passing, failing = linter.lint("HTTP error code E99 fired during the E03 run.", by_id)
    assert passing == ["E03 (active)"]
    assert failing == []
