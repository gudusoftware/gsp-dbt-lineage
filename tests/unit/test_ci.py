import pytest

from gsp_dbt_lineage.ci import CIGuardError, enforce_anonymous_ci_guard, is_ci_environment


def test_no_ci_envvars(monkeypatch):
    for var in ("CI", "GITHUB_ACTIONS", "GITLAB_CI"):
        monkeypatch.delenv(var, raising=False)
    assert is_ci_environment() is False


def test_truthy_ci_var(monkeypatch):
    monkeypatch.setenv("CI", "true")
    assert is_ci_environment() is True


def test_falsey_ci_var(monkeypatch):
    monkeypatch.setenv("CI", "false")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("GITLAB_CI", raising=False)
    assert is_ci_environment() is False


def test_guard_no_op_in_dev(monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    enforce_anonymous_ci_guard("anonymous", 999)


def test_guard_no_op_for_non_anonymous(monkeypatch):
    monkeypatch.setenv("CI", "true")
    enforce_anonymous_ci_guard("authenticated", 999)


def test_guard_under_threshold(monkeypatch):
    monkeypatch.setenv("CI", "true")
    enforce_anonymous_ci_guard("anonymous", 25, threshold=50)


def test_guard_over_threshold_in_ci(monkeypatch):
    monkeypatch.setenv("CI", "true")
    with pytest.raises(CIGuardError) as excinfo:
        enforce_anonymous_ci_guard("anonymous", 60, threshold=50)
    assert "60-node" in str(excinfo.value)
    assert "authenticated" in str(excinfo.value)
