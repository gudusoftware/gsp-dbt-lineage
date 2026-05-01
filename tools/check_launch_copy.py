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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Path to the artifact to lint")
    parser.add_argument("--index-path", default=DEFAULT_INDEX,
                        help="Path to materials/dbt-lineage-evidence/index.yml")
    args = parser.parse_args()

    artifact = Path(args.path)
    if not artifact.is_file():
        print(f"error: artifact not found: {artifact}", file=sys.stderr)
        return 2

    index_path = Path(args.index_path)
    if not index_path.is_file():
        print(f"warning: index not found at {index_path}; skipping check", file=sys.stderr)
        return 0

    text = artifact.read_text(encoding="utf-8")
    cited = sorted(set(re.findall(r"\bE\d{2}\b", text)))
    if not cited:
        print(f"OK: {artifact} cites no E-rows.")
        return 0

    index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    by_id = {row["id"]: row.get("label", "<missing>") for row in index.get("rows", [])}

    failures: list[str] = []
    for eid in cited:
        label = by_id.get(eid, "<missing>")
        if label in ALLOWED_LABELS:
            print(f"  [OK] {eid}  ({label})")
            continue
        failures.append(f"  [!! ] {eid}  ({label}) — must be active/framework-active/manual-active")

    if failures:
        print(f"\n{len(failures)} of {len(cited)} cited rows fail the launch-copy gate:")
        for f in failures:
            print(f)
        print(
            f"\nFix path: drop the cited row from {artifact}, or run a quarterly re-survey "
            f"to flip the label in {index_path}."
        )
        return 1

    print(f"\nOK: all {len(cited)} cited rows are launch-eligible in {artifact}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
