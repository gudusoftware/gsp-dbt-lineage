"""gsp-dbt-lineage CLI entrypoint.

Phase 1: subcommand skeleton with `run --dry-run` (lists nodes/dialects/skip
reasons/SQL paths) and `doctor`. Lineage emission, full `run`, `check`, `diff`,
`emit`, `fixtures` arrive in Phase 2/3.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .artifacts import ArtifactError, read_catalog, read_manifest, read_run_results
from .ci import CIGuardError, enforce_anonymous_ci_guard, is_ci_environment
from .compiled_sql import get_compiled_sql, is_eligible_for_lineage
from .dialect import UnknownAdapterError, resolve_dialect
from .parser_client import (
    BackendConfig,
    DEFAULT_ANONYMOUS_URL,
    DEFAULT_AUTHENTICATED_URL,
    create_backend,
)
from .selector import select_nodes

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_ARGUMENT_ERROR = 2
EXIT_ARTIFACT_ERROR = 10
EXIT_BACKEND_ERROR = 11
EXIT_CI_GUARD = 12
EXIT_UNEXPECTED = 99


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    try:
        if args.command == "run":
            return _cmd_run(args)
        if args.command == "doctor":
            return _cmd_doctor(args)
        if args.command == "version":
            print(__version__)
            return EXIT_OK
        parser.print_help(sys.stderr)
        return EXIT_ARGUMENT_ERROR
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return EXIT_UNEXPECTED


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gsp-dbt-lineage",
        description="Reliable column-level lineage for dbt projects via Gudu SQLFlow.",
    )
    p.add_argument("-v", "--verbose", action="count", default=0, help="-v: info, -vv: debug")
    sub = p.add_subparsers(dest="command", required=False)

    # --- run ---
    r = sub.add_parser("run", help="Read a dbt manifest and produce column lineage.")
    r.add_argument("--manifest", default="target/manifest.json", help="Path to target/manifest.json")
    r.add_argument("--catalog", default="target/catalog.json", help="Optional catalog.json path")
    r.add_argument("--run-results", default="target/run_results.json", help="Optional run_results.json")
    r.add_argument("--target-dir", default="target", help="dbt target dir, used for compiled-SQL fallback")
    r.add_argument("--out", default="target/gudu/column_lineage.json", help="Output path")
    r.add_argument("--select", action="append", default=[], help="dbt-style selector (repeatable)")
    r.add_argument("--exclude", action="append", default=[], help="dbt-style exclude selector")
    r.add_argument("--resource-type", action="append", default=[], help="Filter by resource_type")
    r.add_argument("--dialect", default=None, help="Override adapter→dbvendor mapping")
    r.add_argument("--backend", choices=["anonymous", "authenticated", "self_hosted", "local_jar"],
                   default="anonymous")
    r.add_argument("--url", default=None, help="Backend URL override")
    r.add_argument("--user-id", default=os.environ.get("GSP_USER_ID"))
    r.add_argument("--secret-key", default=os.environ.get("GSP_SECRET_KEY"))
    r.add_argument("--jar-path", default=os.environ.get("GSP_JAR_PATH"))
    r.add_argument("--java-bin", default="java")
    r.add_argument("--timeout", type=int, default=120)
    r.add_argument("--ci-anonymous-threshold", type=int, default=50,
                   help="Refuse anonymous backend in CI above this node count (R2)")
    r.add_argument("--dry-run", action="store_true", help="List nodes/dialects/SQL paths; no parser calls")
    r.add_argument("--deterministic", action="store_true",
                   help="Zero out generated_at and randomize-free; for byte-equal CI runs")
    r.add_argument("--cache-dir", default=".gsp-cache")

    # --- doctor ---
    d = sub.add_parser("doctor", help="Environment diagnostics (Python, dbt, manifest, backend reachability).")
    d.add_argument("--manifest", default="target/manifest.json")
    d.add_argument("--backend", choices=["anonymous", "authenticated", "self_hosted", "local_jar"],
                   default="anonymous")
    d.add_argument("--url", default=None)
    d.add_argument("--jar-path", default=os.environ.get("GSP_JAR_PATH"))

    # --- version ---
    sub.add_parser("version", help="Print the package version and exit.")
    return p


def _setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _cmd_run(args: argparse.Namespace) -> int:
    """Phase 1: implements --dry-run only.

    Phase 2 wires the actual backend dispatch + lineage_mapper + emitters.
    """
    try:
        manifest = read_manifest(args.manifest)
    except ArtifactError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_ARTIFACT_ERROR
    catalog = read_catalog(args.catalog)
    _ = read_run_results(args.run_results)  # not used yet; reserve for run-stat enrichment in Phase 2

    selected_ids = select_nodes(
        nodes=manifest.nodes,
        parent_map=manifest.parent_map,
        child_map=manifest.child_map,
        select=args.select or None,
        exclude=args.exclude or None,
        resource_types=args.resource_type or None,
    )

    plan = []
    eligible_count = 0
    for nid in selected_ids:
        node = manifest.nodes[nid]
        eligible, skip = is_eligible_for_lineage(node)
        sql = get_compiled_sql(node, Path(args.target_dir)) if eligible else None
        if eligible and sql is None:
            eligible = False
            skip = "missing compiled SQL"
        try:
            adapter = manifest.metadata.adapter_type
            dialect = resolve_dialect(adapter, override=args.dialect)
        except UnknownAdapterError as e:
            eligible = False
            skip = f"dialect: {e}"
            dialect = None
        if eligible:
            eligible_count += 1
        plan.append({
            "node_id": nid,
            "name": node.get("name"),
            "resource_type": node.get("resource_type"),
            "dialect": dialect,
            "sql_path": node.get("compiled_path") or node.get("path"),
            "eligible": eligible,
            "skip_reason": skip,
            "compiled_sql_chars": len(sql) if sql else 0,
        })

    try:
        enforce_anonymous_ci_guard(
            backend_mode=args.backend,
            selected_node_count=eligible_count,
            threshold=args.ci_anonymous_threshold,
        )
    except CIGuardError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_CI_GUARD

    if args.dry_run:
        out = {
            "schema_version": "0.2.x",
            "generator": f"gsp-dbt-lineage {__version__}",
            "manifest_metadata": {
                "dbt_version": manifest.metadata.dbt_version,
                "dbt_schema_version": manifest.metadata.dbt_schema_version,
                "project_name": manifest.metadata.project_name,
                "adapter_type": manifest.metadata.adapter_type,
                "selected_count": len(selected_ids),
                "eligible_count": eligible_count,
            },
            "backend": {"mode": args.backend, "dry_run": True},
            "plan": plan,
        }
        print(json.dumps(out, indent=2, sort_keys=True))
        return EXIT_OK

    print(
        "error: full `run` not yet implemented in Phase 1; use --dry-run. "
        "Phase 2 (M1 BigQuery) wires the backend dispatch.",
        file=sys.stderr,
    )
    return EXIT_UNEXPECTED


def _cmd_doctor(args: argparse.Namespace) -> int:
    """Diagnose: Python, dbt installed?, manifest readable?, backend reachable?"""
    checks: list[tuple[str, bool, str]] = []

    # 1. Python version
    py = ".".join(str(x) for x in sys.version_info[:3])
    checks.append(("python", sys.version_info >= (3, 9), f"Python {py} ({'OK' if sys.version_info >= (3, 9) else '< 3.9 unsupported'})"))

    # 2. dbt installed?
    dbt_bin = shutil.which("dbt")
    if dbt_bin:
        checks.append(("dbt", True, f"dbt found at {dbt_bin}"))
    else:
        checks.append(("dbt", False, "dbt not found on PATH (this CLI does not require dbt at runtime, only manifest.json)"))

    # 3. Manifest readable?
    mp = Path(args.manifest)
    if mp.is_file():
        try:
            m = read_manifest(mp)
            checks.append(("manifest", True,
                           f"{mp} OK — dbt {m.metadata.dbt_version}, adapter {m.metadata.adapter_type}, "
                           f"{len(m.nodes)} nodes"))
        except ArtifactError as e:
            checks.append(("manifest", False, f"{mp} unreadable: {e}"))
    else:
        checks.append(("manifest", False, f"{mp} not found (run `dbt build` first)"))

    # 4. CI environment
    checks.append(("environment", True, f"CI detected: {is_ci_environment()}"))

    # 5. Backend reachability (anonymous = HEAD against the URL; auth = GET token-endpoint)
    cfg = BackendConfig(
        mode=args.backend,
        url=args.url,
        jar_path=args.jar_path,
    )
    try:
        backend = create_backend(cfg)
        # Don't actually call the parser — we just report the configured shape.
        url = cfg.effective_url if args.backend != "local_jar" else (args.jar_path or "<unset>")
        checks.append(("backend", True, f"{args.backend} configured: {url}"))
    except (ValueError, Exception) as e:
        checks.append(("backend", False, f"backend create failed: {e}"))

    # Print the report
    width = max(len(name) for name, _, _ in checks)
    failed = 0
    for name, ok, detail in checks:
        glyph = "[OK]" if ok else "[!! ]"
        print(f"  {glyph} {name.ljust(width)}  {detail}")
        if not ok:
            failed += 1
    print()
    print(f"{len(checks) - failed} ok, {failed} failed.")
    return EXIT_OK if failed == 0 else EXIT_BACKEND_ERROR


if __name__ == "__main__":
    sys.exit(main())
