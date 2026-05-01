#!/usr/bin/env python3
"""Phase 5.5 launch-copy linter.

Verifies that every cited evidence ID (E01..E27) in a launch artifact
(README, blog post, landing page, doc) is `active`, `framework-active`, or
`manual-active` per `materials/dbt-lineage-evidence/index.yml`.

Fails the PR if any cited ID is `regression` or `unverified` — this is the
guardrail against marketing copy claiming a fix sqlglot has already shipped.

Usage:
  python tools/check_launch_copy.py README.md
  python tools/check_launch_copy.py docs/quickstart.md
  python tools/check_launch_copy.py path/to/blog-draft.md

The evidence index path is configurable via --index-path; defaults to the
companion ops repo's path on James's dev machine, which is overridable in CI.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

DEFAULT_INDEX = "/home/ubuntu/github/gudu-agent-team/materials/dbt-lineage-evidence/index.yml"

ALLOWED_LABELS = {"active", "framework-active", "manual-active"}


def find_cited_rows(text: str, known_ids: set[str]) -> list[str]:
    """Return E-row IDs cited in `text` that are also present in `known_ids`.

    The regex `\\bE\\d{2}\\b` would match unrelated tokens like "E99" appearing
    in error codes or external references. We bound matches against the index's
    actual ID set so the linter only flags rows the index knows about.
    """
    candidates = set(re.findall(r"\bE\d{2}\b", text))
    return sorted(candidates & known_ids)


def lint(text: str, by_id: dict[str, str]) -> tuple[list[str], list[str]]:
    """Return (passing_ids, failing_messages)."""
    known = set(by_id)
    cited = find_cited_rows(text, known)
    passing: list[str] = []
    failing: list[str] = []
    for eid in cited:
        label = by_id[eid]
        if label in ALLOWED_LABELS:
            passing.append(f"{eid} ({label})")
        else:
            failing.append(f"{eid} ({label}) — must be active/framework-active/manual-active")
    return passing, failing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Path to the artifact to lint")
    parser.add_argument("--index-path", default=DEFAULT_INDEX,
                        help="Path to materials/dbt-lineage-evidence/index.yml")
    parser.add_argument("--strict", action="store_true",
                        help="Fail (exit 2) if the index file is missing instead of warning")
    args = parser.parse_args()

    artifact = Path(args.path)
    if not artifact.is_file():
        print(f"error: artifact not found: {artifact}", file=sys.stderr)
        return 2

    index_path = Path(args.index_path)
    if not index_path.is_file():
        msg = f"index not found at {index_path}"
        if args.strict:
            print(f"FAIL (strict): {msg} — refusing to silently skip the gate", file=sys.stderr)
            return 2
        print(f"warning: {msg}; skipping check (use --strict to fail)", file=sys.stderr)
        return 0

    index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    by_id = {row["id"]: row.get("label", "<missing>") for row in index.get("rows", [])}

    text = artifact.read_text(encoding="utf-8")
    passing, failing = lint(text, by_id)

    for ok in passing:
        print(f"  [OK] {ok}")
    for f in failing:
        print(f"  [!! ] {f}")

    total_cited = len(passing) + len(failing)
    if not total_cited:
        print(f"OK: {artifact} cites no E-rows that are tracked in the index.")
        return 0
    if failing:
        print(f"\n{len(failing)} of {total_cited} cited rows fail the launch-copy gate.")
        print(
            f"Fix path: drop the cited row from {artifact}, or run a quarterly re-survey "
            f"to flip the label in {index_path}."
        )
        return 1

    print(f"\nOK: all {total_cited} cited rows are launch-eligible in {artifact}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
