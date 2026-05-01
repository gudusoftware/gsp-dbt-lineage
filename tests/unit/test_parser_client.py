from unittest.mock import patch

import pytest
import requests

from gsp_dbt_lineage.parser_client import (
    AnonymousBackend,
    AuthenticatedBackend,
    BackendConfig,
    BackendUnavailable,
    ParserError,
    RateLimitError,
    call_with_transient_retry,
    create_backend,
)


class _FakeResponse:
    def __init__(self, status_code: int, json_payload: dict, text: str = ""):
        self.status_code = status_code
        self._json = json_payload
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


def test_anonymous_happy_path():
    b = AnonymousBackend("https://api.example/lineage")
    with patch("requests.post", return_value=_FakeResponse(200, {"code": 200, "data": {}})):
        out = b.get_lineage("SELECT 1", "dbvbigquery")
    assert out["code"] == 200


def test_anonymous_rate_limit_raises():
    b = AnonymousBackend("https://api.example/lineage")
    with patch("requests.post", return_value=_FakeResponse(429, {"upgrade": {}})):
        with pytest.raises(RateLimitError):
            b.get_lineage("SELECT 1", "dbvbigquery")


def test_anonymous_network_error_raises_backend_unavailable():
    b = AnonymousBackend("https://api.example/lineage")
    with patch("requests.post", side_effect=requests.exceptions.ConnectionError("dns")):
        with pytest.raises(BackendUnavailable):
            b.get_lineage("SELECT 1", "dbvbigquery")


def test_token_url_derives_from_lineage_url_cloud():
    b = AuthenticatedBackend(
        url="https://api.gudusoft.com/gspLive_backend/sqlflow/generation/sqlflow/exportFullLineageAsJson",
        user_id="x",
        secret_key="y",
    )
    assert b._token_url() == "https://api.gudusoft.com/gspLive_backend/user/generateToken"


def test_token_url_derives_from_lineage_url_self_hosted():
    b = AuthenticatedBackend(
        url="http://localhost:8165/api/gspLive_backend/sqlflow/generation/sqlflow/exportFullLineageAsJson",
        user_id="x",
        secret_key="y",
    )
    assert b._token_url() == "http://localhost:8165/api/gspLive_backend/user/generateToken"


def test_token_url_raises_when_marker_missing():
    b = AuthenticatedBackend(url="https://example.com/lineage", user_id="x", secret_key="y")
    with pytest.raises(ParserError):
        b._token_url()


def test_authenticated_requires_user_id():
    b = AuthenticatedBackend(url="https://api.gudusoft.com/gspLive_backend/x", user_id=None)
    with pytest.raises(ParserError) as excinfo:
        b.get_lineage("SELECT 1", "dbvbigquery")
    assert "user-id" in str(excinfo.value)


def test_anonymous_5xx_raises_parser_error_for_retry():
    b = AnonymousBackend("https://api.example/lineage")
    with patch("requests.post", return_value=_FakeResponse(503, {})):
        with pytest.raises(ParserError) as excinfo:
            b.get_lineage("SELECT 1", "dbvbigquery")
    assert excinfo.value.status_code == 503


def test_self_hosted_requires_url():
    from gsp_dbt_lineage.parser_client import BackendConfig as _BC
    cfg = _BC(mode="self_hosted")
    with pytest.raises(ParserError):
        _ = cfg.effective_url


def test_authenticated_demo_user_bypasses_token_exchange():
    b = AuthenticatedBackend(
        url="https://api.gudusoft.com/gspLive_backend/x",
        user_id="gudu|0123456789",
        secret_key="ignored",
    )
    with patch("requests.post", return_value=_FakeResponse(200, {"code": 200, "data": {}})):
        out = b.get_lineage("SELECT 1", "dbvbigquery")
    assert out["code"] == 200


def test_create_backend_anonymous_default_url():
    cfg = BackendConfig(mode="anonymous")
    b = create_backend(cfg)
    assert isinstance(b, AnonymousBackend)
    assert "anonymous" in b.url


def test_create_backend_unknown_mode_raises():
    with pytest.raises(ValueError):
        create_backend(BackendConfig(mode="not-a-mode"))


def test_transient_retry_eventually_succeeds():
    b = AnonymousBackend("https://x/y")
    calls = {"n": 0}

    def fake_post(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.exceptions.ConnectionError("flap")
        return _FakeResponse(200, {"code": 200, "data": {}})

    with patch("requests.post", side_effect=fake_post):
        out = call_with_transient_retry(b, "SELECT 1", "dbvbigquery", retries=3, initial_backoff=0.0)
    assert out["code"] == 200
    assert calls["n"] == 3


def test_transient_retry_does_not_retry_rate_limit():
    b = AnonymousBackend("https://x/y")
    with patch("requests.post", return_value=_FakeResponse(429, {})):
        with pytest.raises(RateLimitError):
            call_with_transient_retry(b, "SELECT 1", "dbvbigquery", retries=5, initial_backoff=0.0)
