"""CI-environment detection + anonymous-mode guardrail.

Per plan §6.2 task 1.9 + risk R2: if a CI build runs against the anonymous tier
on a project with >50 nodes, it will exhaust the daily quota in a single run.
Refuse with an actionable error before the first network call.

Threshold (50) is configurable via CLI to satisfy R2's tighten-trigger.
"""

from __future__ import annotations

import os

# Standard env vars set by mainstream CI providers.
CI_ENV_VARS = (
    "CI",
    "GITHUB_ACTIONS",
    "GITLAB_CI",
    "CIRCLECI",
    "TRAVIS",
    "BUILDKITE",
    "TEAMCITY_VERSION",
    "JENKINS_URL",
    "DBT_CLOUD_RUN_ID",  # dbt Cloud
    "AZURE_HTTP_USER_AGENT",  # Azure Pipelines
)


def is_ci_environment() -> bool:
    """Return True if any well-known CI env var is set to a truthy value."""
    for var in CI_ENV_VARS:
        val = os.environ.get(var, "")
        if val and val.lower() not in {"false", "0", "no", ""}:
            return True
    return False


class CIGuardError(RuntimeError):
    """Raised when CI auto-detection refuses to proceed in anonymous mode."""


def enforce_anonymous_ci_guard(
    backend_mode: str,
    selected_node_count: int,
    threshold: int = 50,
) -> None:
    """Refuse anonymous-mode runs above the threshold in CI.

    Raises CIGuardError with an actionable message. In dev (non-CI),
    no-op regardless of count.
    """
    if backend_mode != "anonymous":
        return
    if not is_ci_environment():
        return
    if selected_node_count <= threshold:
        return
    raise CIGuardError(
        f"refuses anonymous backend in CI for a {selected_node_count}-node selection "
        f"(threshold {threshold}). The 50/day per-IP anonymous quota will be "
        f"exhausted within a single CI run. Choose one:\n"
        f"  1. Switch to authenticated mode: --backend authenticated --user-id $GSP_USER_ID --secret-key $GSP_SECRET_KEY\n"
        f"  2. Self-host the parser:        --backend self_hosted --url http://your-host:8165/api\n"
        f"  3. Use the local JAR:           --backend local_jar --jar-path /path/to/gsp.jar\n"
        f"  4. Reduce the selection (--select / --exclude) below {threshold} nodes.\n"
        f"To disable this guard, set the threshold higher (--ci-anonymous-threshold N)."
    )
