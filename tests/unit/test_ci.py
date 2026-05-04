import pytest

from gsp_dbt_lineage.ci import CI_ENV_VARS, CIGuardError, enforce_anonymous_ci_guard, is_ci_environment


def _scrub_ci_env(monkeypatch):
    """Clear every CI env var the detector knows about — required when these
    tests run inside a real CI runner (GitHub Actions sets GITHUB_ACTIONS
    alongside CI; deleting only CI leaves the detector firing)."""
    for var in CI_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_no_ci_envvars(monkeypatch):
    _scrub_ci_env(monkeypatch)
    assert is_ci_environment() is False


def test_truthy_ci_var(monkeypatch):
    monkeypatch.setenv("CI", "true")
    assert is_ci_environment() is True


def test_falsey_ci_var(monkeypatch):
    _scrub_ci_env(monkeypatch)
    monkeypatch.setenv("CI", "false")
    assert is_ci_environment() is False


def test_guard_no_op_in_dev(monkeypatch):
    _scrub_ci_env(monkeypatch)
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
