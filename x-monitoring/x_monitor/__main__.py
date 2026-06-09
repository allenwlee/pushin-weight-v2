# {{AGENT_ATTRIBUTION}}
"""x-monitor CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure we run from the package root regardless of cwd.
_PKG_ROOT = Path(__file__).resolve().parent.parent


def _project_paths() -> dict[str, Path]:
    """Resolve project paths. Prefer cwd-relative; fall back to package root.

    The CLI works against the project tree in cwd (so test fixtures and
    local development can use a tmp project) but also works when invoked
    from any cwd if the package was installed in editable mode from the
    x-monitoring project.
    """
    cwd = Path.cwd()
    cwd_config = cwd / "config.yaml"
    if cwd_config.exists():
        root = cwd
    else:
        root = _PKG_ROOT
    return {
        "config": root / "config.yaml",
        "data": root / "data",
        "db": root / "data" / "x_monitoring.db",
        "queries": root / "data" / "queries",
        "accounts": root / "data" / "accounts",
        "review": root / "data" / "_review_queue.json",
    }


def _load_config_or_die(path: Path):
    from x_monitor.config import load_config
    from pydantic import ValidationError

    try:
        return load_config(path)
    except ValidationError as e:
        print(f"config error: {e}", file=sys.stderr)
        sys.exit(2)


def cmd_run(args, paths) -> int:
    from x_monitor.apify import TwitterApiClient
    from x_monitor.run import RunPipeline

    cfg = _load_config_or_die(paths["config"])
    api: TwitterApiClient
    if args.dry_run:
        # In dry-run we don't need a real client; use a stub.
        api = TwitterApiClient(api_key="dry-run")
    else:
        try:
            api = TwitterApiClient.from_env()
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
    pipeline = RunPipeline(cfg, paths["data"], db_path=paths["db"])
    summary = pipeline.execute(
        api,
        model_filter=args.models.split(",") if args.models else None,
        query_filter=args.queries.split(",") if args.queries else None,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    if args.dry_run:
        # Print the per-model, per-query list
        print("\n--- Estimated cost per model ---", file=sys.stderr)
        from x_monitor.queries import load_queries

        total = 0
        for m in (args.models.split(",") if args.models else cfg.enabled_models):
            try:
                qs = load_queries(m, paths["data"])
            except Exception as e:
                print(f"  {m}: ERROR {e}", file=sys.stderr)
                continue
            from x_monitor.queries import estimated_cost

            cost = estimated_cost(qs)
            total += cost
            print(f"  {m}: {cost}", file=sys.stderr)
        print(f"  TOTAL: {total} (ceiling: {cfg.daily_ceiling})", file=sys.stderr)
    return 0 if summary.get("status") in ("completed", "degraded", "dry_run") else 1


def cmd_dry_run(args, paths) -> int:
    return cmd_run(argparse.Namespace(dry_run=True, models=getattr(args, "models", None), queries=None), paths)


def cmd_dashboard(args, paths) -> int:
    from x_monitor.dashboard import DashboardApp

    cfg = _load_config_or_die(paths["config"])
    app = DashboardApp(cfg, paths["data"], db_path=paths["db"])
    if args.action == "start":
        try:
            pid = app.start_background()
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(f"dashboard started, pid={pid}, port={cfg.dashboard.port}")
        return 0
    if args.action == "stop":
        ok = DashboardApp.stop_background(paths["data"])
        if ok:
            print("dashboard stopped")
            return 0
        print("no running dashboard (no pid file)", file=sys.stderr)
        return 1
    if args.action == "status":
        st = DashboardApp.status(paths["data"])
        print(json.dumps(st, indent=2))
        return 0 if st.get("running") else 1
    print(f"unknown action: {args.action}", file=sys.stderr)
    return 2


def cmd_review(args, paths) -> int:
    from x_monitor.review import ReviewQueue

    q = ReviewQueue(paths["review"])
    if args.review_action == "list":
        items = q.list(status=args.status)
        for it in items:
            print(
                f"{it.get('status','?'):9s} {it.get('tweet_id','?'):20s} "
                f"{it.get('reason','?'):20s} {it.get('model_id','')}"
            )
        return 0
    if args.review_action == "add":
        if not args.tweet_id or not args.reason:
            print("--add requires --tweet-id and --reason", file=sys.stderr)
            return 2
        e = q.add(args.tweet_id, reason=args.reason, note=args.note or "", model_id=args.model)
        print(json.dumps(e, indent=2, ensure_ascii=False))
        return 0
    if args.review_action == "resolve":
        e = q.resolve(args.tweet_id, note=args.note or "")
        return 0 if e else 2
    if args.review_action == "dismiss":
        e = q.dismiss(args.tweet_id, note=args.note or "")
        return 0 if e else 2
    print(f"unknown review action: {args.review_action}", file=sys.stderr)
    return 2


def cmd_migrate(args, paths) -> int:
    from x_monitor.store import Store

    store = Store(paths["db"], auto_migrate=False)
    try:
        applied = store.apply_migrations()
        print(f"applied: {applied}")
        return 0
    finally:
        store.close()


def cmd_accounts(args, paths) -> int:
    from x_monitor.accounts import load_accounts
    from x_monitor.apify import TwitterApiClient

    if args.accounts_action == "bootstrap-followers":
        if not args.model or not args.handle:
            print("--model and --handle required", file=sys.stderr)
            return 2
        try:
            api = TwitterApiClient.from_env()
        except Exception as e:
            print(f"twitterapi.io error: {e}", file=sys.stderr)
            return 2
        followers = api.run_followers(args.handle, max_results=200)
        # Append to data/accounts/<model>.yaml under a `discovered_followers`
        # section; do not modify the seeded 'accounts' list.
        import yaml

        yaml_path = paths["accounts"] / f"{args.model}.yaml"
        existing = {}
        if yaml_path.exists():
            existing = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        existing.setdefault("discovered_followers", [])
        for f in followers:
            if not any(df.get("handle") == f["handle"] for df in existing["discovered_followers"]):
                existing["discovered_followers"].append(f)
        yaml_path.write_text(
            yaml.safe_dump(existing, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        print(f"wrote {len(followers)} followers to {yaml_path}")
        return 0
    if args.accounts_action == "list":
        for m in args.model.split(",") if args.model else []:
            try:
                accts = load_accounts(m, paths["data"])
                print(f"\n[{m}]")
                for a in accts:
                    print(f"  @{a.handle}  role={a.role}  verified={a.verified}")
            except Exception as e:
                print(f"  {m}: {e}")
        return 0
    print(f"unknown accounts action: {args.accounts_action}", file=sys.stderr)
    return 2


def cmd_queries(args, paths) -> int:
    from x_monitor.queries import load_queries, validate_query_syntax

    if args.queries_action == "list-disabled":
        cfg = _load_config_or_die(paths["config"])
        for m in cfg.enabled_models:
            try:
                qs = load_queries(m, paths["data"])
            except Exception as e:
                print(f"  {m}: {e}")
                continue
            for q in qs:
                if not q.enabled:
                    print(f"  {m}/{q.id}: disabled  ({q.notes or 'no notes'})")
        return 0
    if args.queries_action == "validate":
        cfg = _load_config_or_die(paths["config"])
        any_errors = False
        for m in cfg.enabled_models:
            try:
                qs = load_queries(m, paths["data"])
            except Exception as e:
                print(f"  {m}: load error: {e}")
                any_errors = True
                continue
            for q in qs:
                errs = validate_query_syntax(q)
                if errs:
                    any_errors = True
                    print(f"  {m}/{q.id}: {errs}")
        return 1 if any_errors else 0
    print(f"unknown queries action: {args.queries_action}", file=sys.stderr)
    return 2


def cmd_setup(args, paths) -> int:
    if args.setup_action == "twitterapi-key":
        # Just confirms the key is in env; the env file path is informational.
        from x_monitor.apify import TwitterApiClient

        try:
            api = TwitterApiClient.from_env()
            print(
                f"OK: TWITTERAPI_IO_API_KEY present (prefix={api.api_key[:4]}...)"
            )
            return 0
        except Exception as e:
            print(
                f"FAIL: {e}\n"
                f"Add to ~/.env.secrets:\n"
                f"  export TWITTERAPI_IO_API_KEY=\"...\"",
                file=sys.stderr,
            )
            return 1
    print(f"unknown setup action: {args.setup_action}", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="x-monitor", description="x-monitor CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run the daily harvest")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--models", help="comma-separated model_id filter")
    p_run.add_argument("--queries", help="comma-separated query_id filter (Q1..Q6)")
    p_run.set_defaults(func=cmd_run)

    p_dr = sub.add_parser("dry-run", help="Alias for `run --dry-run`")
    p_dr.add_argument("--models", help="comma-separated model_id filter")
    p_dr.set_defaults(func=cmd_dry_run)

    p_dash = sub.add_parser("dashboard", help="Start/stop/status the dashboard")
    p_dash.add_argument("action", choices=["start", "stop", "status"])
    p_dash.set_defaults(func=cmd_dashboard)

    p_rev = sub.add_parser("review", help="Manage the review queue")
    p_rev.add_argument(
        "review_action", choices=["list", "add", "resolve", "dismiss"]
    )
    p_rev.add_argument("--tweet-id", dest="tweet_id")
    p_rev.add_argument("--reason")
    p_rev.add_argument("--note", default="")
    p_rev.add_argument("--model", default=None)
    p_rev.add_argument("--status", default=None, choices=["open", "resolved", "dismissed"])
    p_rev.set_defaults(func=cmd_review)

    p_mig = sub.add_parser("migrate", help="Apply forward-only DB migrations")
    p_mig.set_defaults(func=cmd_migrate)

    p_acc = sub.add_parser("accounts", help="Account-graph operations")
    p_acc.add_argument(
        "accounts_action", choices=["bootstrap-followers", "list"]
    )
    p_acc.add_argument("--model")
    p_acc.add_argument("--handle")
    p_acc.set_defaults(func=cmd_accounts)

    p_q = sub.add_parser("queries", help="Query-library operations")
    p_q.add_argument("queries_action", choices=["list-disabled", "validate"])
    p_q.set_defaults(func=cmd_queries)

    p_set = sub.add_parser("setup", help="One-time setup wizards")
    p_set.add_argument("setup_action", choices=["twitterapi-key"])
    p_set.set_defaults(func=cmd_setup)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    paths = _project_paths()
    if not paths["config"].exists():
        print(f"config not found: {paths['config']}", file=sys.stderr)
        return 2
    paths["data"].mkdir(parents=True, exist_ok=True)
    return args.func(args, paths)


if __name__ == "__main__":
    sys.exit(main())
