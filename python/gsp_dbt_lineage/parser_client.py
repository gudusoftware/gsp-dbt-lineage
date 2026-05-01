"""SQLFlow backend client — calls api.gudusoft.com / self-hosted Docker / local JAR.

Ported and trimmed from `gsp-datahub-sidecar/src/gsp_datahub_sidecar/backend.py`
(Apache-2.0). Adjusted for dbt-lineage's needs: no DataHub-specific concerns,
explicit timeouts, structured retries with exponential backoff for transient
network errors only (NOT for token-refresh, which is its own targeted retry).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Default lineage endpoint. The path matches GSP/SQLFlow's stable API contract.
DEFAULT_ANONYMOUS_URL = "https://api.gudusoft.com/gspLive_backend/api/anonymous/lineage"
DEFAULT_AUTHENTICATED_URL = "https://api.gudusoft.com/gspLive_backend/sqlflow/generation/sqlflow/exportFullLineageAsJson"


class ParserError(Exception):
    """Raised when the SQLFlow parser/API returns an error."""

    def __init__(
        self,
        message: str,
        status_code: int = 0,
        response_body: dict | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body or {}


class RateLimitError(ParserError):
    """Anonymous tier exceeded its 50/day per-IP quota."""


class BackendUnavailable(ParserError):
    """Backend is unreachable (DNS, connection refused, repeated 5xx)."""


@dataclass
class BackendConfig:
    """Single config object covering all 4 modes."""
    mode: str  # one of: anonymous, authenticated, self_hosted, local_jar
    url: str | None = None
    user_id: str | None = None
    secret_key: str | None = None
    jar_path: str | None = None
    java_bin: str = "java"
    timeout_seconds: int = 120
    transient_retries: int = 2  # for 5xx / connection reset; not for 4xx

    @property
    def effective_url(self) -> str:
        if self.url:
            return self.url
        if self.mode == "anonymous":
            return DEFAULT_ANONYMOUS_URL
        return DEFAULT_AUTHENTICATED_URL


class Backend(ABC):
    """Abstract backend. Subclasses implement get_lineage."""

    @abstractmethod
    def get_lineage(self, sql: str, db_vendor: str, **kwargs) -> dict[str, Any]:
        ...

    @staticmethod
    def _payload(sql: str, db_vendor: str, **kwargs) -> dict[str, str]:
        return {
            "sqltext": sql,
            "dbvendor": db_vendor,
            "showRelationType": kwargs.get("show_relation_type", "fdd"),
        }


class AnonymousBackend(Backend):
    """50 calls/day per IP. No auth. Eval-only."""

    def __init__(self, url: str, timeout: int = 120):
        self.url = url
        self.timeout = timeout

    def get_lineage(self, sql: str, db_vendor: str, **kwargs) -> dict[str, Any]:
        payload = self._payload(sql, db_vendor, **kwargs)
        try:
            resp = requests.post(self.url, json=payload, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            raise BackendUnavailable(f"anonymous backend unreachable: {e}") from e
        if resp.status_code == 429:
            try:
                body = resp.json()
            except json.JSONDecodeError:
                body = {}
            raise RateLimitError(
                "anonymous tier rate-limited (50/day per IP). "
                "Get a free personal key (10k/month) or self-host: "
                "https://docs.gudusoft.com/sign-up/",
                status_code=429,
                response_body=body,
            )
        resp.raise_for_status()
        return resp.json()


class _TokenExchangeBackend(Backend):
    """Shared base for ``authenticated`` (cloud) and ``self_hosted`` modes.

    Two-step protocol:
      1. POST `.../user/generateToken` with userId + secretKey (form-encoded) -> JWT.
      2. POST the lineage endpoint with userId + token (form-encoded).

    Demo user `gudu|0123456789` accepts the literal string "token" without exchange.
    """

    label: str = "SQLFlow"

    def __init__(
        self,
        url: str,
        user_id: str | None = None,
        secret_key: str | None = None,
        timeout: int = 120,
    ):
        self.url = url
        self.user_id = user_id
        self.secret_key = secret_key
        self.timeout = timeout
        self._token: str | None = None

    def _token_url(self) -> str:
        marker = "/gspLive_backend/"
        idx = self.url.find(marker)
        if idx == -1:
            raise ParserError(
                f"cannot derive generateToken URL from {self.url} — "
                f"expected '/gspLive_backend/' in the path."
            )
        return self.url[: idx + len(marker)] + "user/generateToken"

    def _get_token(self) -> str:
        if self._token:
            return self._token
        if self.user_id == "gudu|0123456789":
            self._token = "token"
            return self._token
        if not self.user_id or not self.secret_key:
            raise ParserError(
                f"{self.label} requires user_id + secret_key. "
                f"Pass --user-id / --secret-key or set GSP_USER_ID / GSP_SECRET_KEY."
            )
        token_url = self._token_url()
        logger.debug("requesting %s token from %s", self.label, token_url)
        try:
            resp = requests.post(
                token_url,
                data={"userId": self.user_id, "secretKey": self.secret_key},
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as e:
            raise BackendUnavailable(f"{self.label} token endpoint unreachable: {e}") from e
        if resp.status_code != 200:
            raise ParserError(
                f"{self.label} token request to {token_url} returned HTTP {resp.status_code}. "
                f"Response: {resp.text[:500]}",
                status_code=resp.status_code,
            )
        body = resp.json()
        if str(body.get("code")) != "200" or not body.get("token"):
            raise ParserError(
                f"{self.label} token generation failed: {body.get('error') or body}",
                response_body=body,
            )
        self._token = body["token"]
        return self._token

    def get_lineage(self, sql: str, db_vendor: str, **kwargs) -> dict[str, Any]:
        payload = self._payload(sql, db_vendor, **kwargs)
        if self.user_id:
            payload["userId"] = self.user_id
            payload["token"] = self._get_token()

        try:
            resp = requests.post(self.url, data=payload, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            raise BackendUnavailable(f"{self.label} unreachable: {e}") from e
        if resp.status_code != 200:
            raise ParserError(
                f"{self.label} returned HTTP {resp.status_code} from {self.url}. "
                f"Response: {resp.text[:500]}",
                status_code=resp.status_code,
            )
        body = resp.json()
        code = body.get("code") if isinstance(body, dict) else None
        if code not in (None, 200, "200"):
            # Targeted retry: a 401 response means the cached token expired.
            if str(code) == "401" and self._token is not None:
                logger.info("%s token rejected — refreshing once.", self.label)
                self._token = None
                payload["token"] = self._get_token()
                resp = requests.post(self.url, data=payload, timeout=self.timeout)
                body = resp.json()
                code = body.get("code") if isinstance(body, dict) else None
            if code not in (None, 200, "200"):
                raise ParserError(
                    f"{self.label} returned error code {code}: {body.get('error') or body}",
                    status_code=int(code) if str(code).isdigit() else 0,
                    response_body=body,
                )
        return body


class AuthenticatedBackend(_TokenExchangeBackend):
    label = "Authenticated SQLFlow"


class SelfHostedBackend(_TokenExchangeBackend):
    label = "Self-hosted SQLFlow"


class LocalJarBackend(Backend):
    """Embedded gsp.jar via JVM subprocess. SQL never leaves the process."""

    label = "Local JAR"

    def __init__(self, jar_path: str, java_bin: str = "java", timeout: int = 120):
        self.jar_path = jar_path
        self.java_bin = java_bin
        self.timeout = timeout

    def get_lineage(self, sql: str, db_vendor: str, **kwargs) -> dict[str, Any]:
        if not os.path.isfile(self.jar_path):
            raise ParserError(
                f"{self.label}: jar not found at {self.jar_path!r}. "
                f"Set --jar-path or GSP_JAR_PATH."
            )
        if shutil.which(self.java_bin) is None and not os.path.isfile(self.java_bin):
            raise ParserError(
                f"{self.label}: java executable {self.java_bin!r} not found on PATH. "
                f"Install JRE 8+ or set --java-bin."
            )
        with tempfile.NamedTemporaryFile(
            "w", suffix=".sql", prefix="gsp_", delete=False, encoding="utf-8"
        ) as f:
            f.write(sql)
            tmp = f.name
        try:
            cmd = [
                self.java_bin, "-cp", self.jar_path,
                "gudusoft.gsqlparser.dlineage.DataFlowAnalyzer",
                "/f", tmp,
                "/t", _short_vendor(db_vendor),
                "/json",
            ]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
            except subprocess.TimeoutExpired as e:
                raise ParserError(f"{self.label}: JAR timed out after {self.timeout}s") from e
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        if proc.returncode != 0:
            raise ParserError(
                f"{self.label}: java exited with code {proc.returncode}. "
                f"stderr: {proc.stderr.strip()[:500]}",
                status_code=proc.returncode,
            )
        try:
            dataflow = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise ParserError(
                f"{self.label}: stdout is not JSON: {e}. "
                f"First 200 chars: {proc.stdout[:200]!r}"
            ) from e
        return {"code": 200, "data": dataflow}


def _short_vendor(db_vendor: str) -> str:
    """Strip the dbv prefix for the JAR CLI (which only accepts the short form)."""
    name = (db_vendor or "").strip().lower()
    if name.startswith("dbv"):
        name = name[3:]
    return name or "generic"


def create_backend(config: BackendConfig) -> Backend:
    """Factory: produce the right Backend instance for a config."""
    if config.mode == "local_jar":
        return LocalJarBackend(
            jar_path=config.jar_path or "",
            java_bin=config.java_bin,
            timeout=config.timeout_seconds,
        )
    url = config.effective_url
    if config.mode == "anonymous":
        return AnonymousBackend(url=url, timeout=config.timeout_seconds)
    if config.mode == "authenticated":
        return AuthenticatedBackend(
            url=url,
            user_id=config.user_id,
            secret_key=config.secret_key,
            timeout=config.timeout_seconds,
        )
    if config.mode == "self_hosted":
        return SelfHostedBackend(
            url=url,
            user_id=config.user_id,
            secret_key=config.secret_key,
            timeout=config.timeout_seconds,
        )
    raise ValueError(f"unknown backend mode: {config.mode}")


def call_with_transient_retry(
    backend: Backend,
    sql: str,
    db_vendor: str,
    *,
    retries: int = 2,
    initial_backoff: float = 1.0,
    **kwargs,
) -> dict[str, Any]:
    """Call backend.get_lineage with retry on transient failures.

    Retries on:
      - BackendUnavailable (network/DNS/connection-reset)
      - 5xx responses (raised as ParserError with status_code in 500-599)

    Does NOT retry on:
      - RateLimitError (anonymous tier quota — must wait)
      - ParserError with status < 500 (auth failure, bad request, etc.)
    """
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return backend.get_lineage(sql, db_vendor, **kwargs)
        except RateLimitError:
            raise
        except BackendUnavailable as e:
            last = e
        except ParserError as e:
            if 500 <= e.status_code < 600:
                last = e
            else:
                raise
        if attempt < retries:
            delay = initial_backoff * (2 ** attempt)
            logger.warning("transient parser failure (attempt %d): %s — retrying in %.1fs", attempt + 1, last, delay)
            time.sleep(delay)
    assert last is not None
    raise last
