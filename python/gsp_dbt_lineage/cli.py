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

from . import __schema_version__, __version__
from .artifacts import ArtifactError, read_catalog, read_manifest, read_run_results
from .cache import FileCache, cache_key
from .ci import CIGuardError, enforce_anonymous_ci_guard, is_ci_environment
from .compiled_sql import get_compiled_sql, is_eligible_for_lineage
from .confidence import annotate_dynamic_sql
from .dialect import UnknownAdapterError, resolve_dialect
from .emitters import datahub as datahub_emitter
from .emitters import json as json_emitter
from .lineage_mapper import map_gsp_to_node
from .lineage_schema import SchemaError, validate_lineage
from .parser_client import (
    BackendConfig,
    BackendUnavailable,
    DEFAULT_ANONYMOUS_URL,
    DEFAULT_AUTHENTICATED_URL,
    ParserError,
    RateLimitError,
    call_with_transient_retry,
    create_backend,
)
from .redact import redact as _redact
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
        if args.command == "emit":
            return _cmd_emit(args)
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
    r.add_argument("--no-cache", action="store_true", help="Bypass the SQL-hash cache")
    r.add_argument("--redact-literals", action="store_true",
                   help="Replace string and numeric literals before sending SQL to the backend")
    r.add_argument("--retries", type=int, default=2,
                   help="Transient-failure retries (5xx, network reset)")

    # --- emit ---
    e = sub.add_parser("emit", help="Convert column_lineage.json to a target catalog format.")
    e.add_argument("target", choices=["datahub"], help="Output format")
    e.add_argument("--lineage", required=True, help="Path to column_lineage.json")
    e.add_argument("--out", required=True, help="Output path")
    e.add_argument("--env", default="PROD", help="DataHub environment name (PROD/DEV/...)")

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

    manifest_meta = {
        "dbt_version": manifest.metadata.dbt_version,
        "dbt_schema_version": manifest.metadata.dbt_schema_version,
        "project_name": manifest.metadata.project_name,
        "adapter_type": manifest.metadata.adapter_type,
        "selected_count": len(selected_ids),
        "eligible_count": eligible_count,
    }

    if args.dry_run:
        out = {
            "schema_version": __schema_version__,
            "generator": f"gsp-dbt-lineage {__version__}",
            "manifest_metadata": manifest_meta,
            "backend": {"mode": args.backend, "dry_run": True},
            "plan": plan,
        }
        print(json.dumps(out, indent=2, sort_keys=True))
        return EXIT_OK

    # Wire the backend.
    cfg = BackendConfig(
        mode=args.backend,
        url=args.url,
        user_id=args.user_id,
        secret_key=args.secret_key,
        jar_path=args.jar_path,
        java_bin=args.java_bin,
        timeout_seconds=args.timeout,
    )
    try:
        backend = create_backend(cfg)
    except (ParserError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_BACKEND_ERROR

    cache = None if args.no_cache else FileCache(args.cache_dir)

    nodes_out: list[dict[str, Any]] = []
    stats = {"parsed": 0, "partial": 0, "unsupported": 0, "failed": 0, "skipped": 0,
             "total_columns": 0, "resolved_columns": 0}
    parser_version = "unknown"

    for entry in plan:
        nid = entry["node_id"]
        if not entry["eligible"]:
            stats["skipped"] += 1
            nodes_out.append({
                "node_id": nid, "status": "skipped",
                "confidence": "low", "dialect": entry["dialect"],
                "upstream_tables": [], "downstream": [], "columns": [],
                "unresolved": [{"reason": "skipped", "detail": entry["skip_reason"]}],
                "warnings": [],
            })
            continue

        node = manifest.nodes[nid]
        sql = get_compiled_sql(node, Path(args.target_dir))
        if sql is None:
            stats["failed"] += 1
            nodes_out.append({
                "node_id": nid, "status": "failed",
                "confidence": "low", "dialect": entry["dialect"],
                "upstream_tables": [], "downstream": [], "columns": [],
                "unresolved": [{"reason": "compiled_sql_unreadable"}], "warnings": [],
            })
            continue

        if args.redact_literals:
            sql = _redact(sql)

        # Cache lookup.
        ck = cache_key(sql, entry["dialect"], args.backend, parser_version, __version__)
        cached = cache.get(ck) if cache else None
        if cached is not None:
            response = cached
        else:
            try:
                response = call_with_transient_retry(
                    backend, sql, entry["dialect"], retries=args.retries
                )
            except RateLimitError as e:
                print(f"error: {e}", file=sys.stderr)
                return EXIT_BACKEND_ERROR
            except (BackendUnavailable, ParserError) as e:
                logger.warning("node %s: %s", nid, e)
                stats["failed"] += 1
                nodes_out.append({
                    "node_id": nid, "status": "failed",
                    "confidence": "low", "dialect": entry["dialect"],
                    "upstream_tables": [], "downstream": [], "columns": [],
                    "unresolved": [{"reason": "parser_error", "detail": str(e)[:200]}],
                    "warnings": [],
                })
                continue
            if cache:
                cache.put(ck, response)

        # Map response → node.
        node_out = map_gsp_to_node(response, node_id=nid, dialect=entry["dialect"])
        node_out["downstream"] = sorted(manifest.child_map.get(nid, []) or [])
        node_out = annotate_dynamic_sql(node_out, sql)

        stats[node_out["status"]] = stats.get(node_out["status"], 0) + 1
        stats["total_columns"] += len(node_out["columns"])
        stats["resolved_columns"] += sum(1 for c in node_out["columns"] if c.get("upstream"))
        nodes_out.append(node_out)

    if stats["total_columns"]:
        stats["coverage"] = round(stats["resolved_columns"] / stats["total_columns"], 4)
    else:
        stats["coverage"] = 0.0

    backend_block = {
        "mode": args.backend,
        "parser_version": parser_version,
        "cli_version": __version__,
    }
    if cache:
        backend_block["cache_stats"] = cache.stats()

    doc = json_emitter.render(
        schema_version=__schema_version__,
        generator=f"gsp-dbt-lineage {__version__}",
        manifest_metadata=manifest_meta,
        backend=backend_block,
        stats=stats,
        nodes=nodes_out,
        deterministic=args.deterministic,
    )

    try:
        validate_lineage(doc)
    except SchemaError as e:
        print(f"error: emitted document failed schema validation: {e}", file=sys.stderr)
        return EXIT_UNEXPECTED

    json_emitter.write(doc, args.out)
    print(f"wrote {args.out} — {stats['parsed']} parsed, {stats['partial']} partial, "
          f"{stats['failed']} failed, {stats['skipped']} skipped, "
          f"coverage {stats['coverage']:.0%}")
    return EXIT_OK


def _cmd_emit(args: argparse.Namespace) -> int:
    """Convert column_lineage.json -> target catalog format."""
    p = Path(args.lineage)
    if not p.is_file():
        print(f"error: lineage doc not found: {p}", file=sys.stderr)
        return EXIT_ARTIFACT_ERROR
    doc = json.loads(p.read_text(encoding="utf-8"))
    if args.target == "datahub":
        mcps = datahub_emitter.emit(doc, env=args.env)
        datahub_emitter.write(mcps, args.out)
        print(f"wrote {args.out} — {len(mcps)} MCPs")
        return EXIT_OK
    print(f"error: unsupported target {args.target!r}", file=sys.stderr)
    return EXIT_ARGUMENT_ERROR


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

    # 5. Backend reachability — actually probe.
    cfg = BackendConfig(mode=args.backend, url=args.url, jar_path=args.jar_path)
    if args.backend == "local_jar":
        jar_path = args.jar_path or ""
        if not jar_path:
            checks.append(("backend", False, "local_jar: --jar-path / GSP_JAR_PATH not set"))
        elif not Path(jar_path).is_file():
            checks.append(("backend", False, f"local_jar: jar not found at {jar_path}"))
        else:
            java_bin = shutil.which("java")
            if java_bin:
                checks.append(("backend", True, f"local_jar: jar OK ({jar_path}); java at {java_bin}"))
            else:
                checks.append(("backend", False, f"local_jar: jar OK ({jar_path}) but `java` not on PATH"))
    else:
        try:
            url = cfg.effective_url
        except Exception as e:
            checks.append(("backend", False, f"{args.backend}: {e}"))
        else:
            try:
                import requests
                # HEAD often blocked on these endpoints; GET with short timeout instead.
                resp = requests.get(url, timeout=10)
                # Any HTTP response (including 4xx) means the endpoint is up.
                checks.append(("backend", True, f"{args.backend} reachable: {url} (HTTP {resp.status_code})"))
            except Exception as e:
                checks.append(("backend", False, f"{args.backend} unreachable at {url}: {e}"))

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
