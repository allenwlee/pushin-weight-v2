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
                f"{it.get('reason','?'):20s} {it.get('brand_id','')}"
            )
        return 0
    if args.review_action == "add":
        if not args.tweet_id or not args.reason:
            print("--add requires --tweet-id and --reason", file=sys.stderr)
            return 2
        e = q.add(args.tweet_id, reason=args.reason, note=args.note or "", brand_id=args.model)
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


def cmd_relevance(args, paths) -> int:
    """Manage per-model relevance filter YAMLs.

    Subcommands (v1.2):
      list           - show all 7 model filter configs (table)
      dry-run        - apply filter to a hardcoded fixture (commit 2)
      audit-handles  - probe canonical_handles via TwitterAPI.io (commit 2)
      backfill       - fetch headlines for URL-only DB rows (commit 3)
    """
    action = args.relevance_action
    return _dispatch_relevance(args, action, paths)


def _now_iso_for_audit() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _dispatch_relevance(args, action: str, paths) -> int:
    from x_monitor.config import KNOWN_MODELS
    from x_monitor.relevance import load_filter
    if action == "list":
        # Header
        print(
            f"{'model':<18} {'canonical':<10} {'must_any':<8} "
            f"{'cjk':<4} {'banned':<6} {'verified':<12} notes"
        )
        print("-" * 100)
        for m in sorted(KNOWN_MODELS):
            cfg = load_filter(m, paths["data"])
            notes_short = (cfg.notes or "").split("\n")[0][:30]
            print(
                f"{m:<18} {len(cfg.canonical_handles):<10} "
                f"{len(cfg.must_have_any):<8} {len(cfg.cjk_tokens):<4} "
                f"{len(cfg.must_have_none):<6} "
                f"{(cfg.verified_at or 'NOT AUDITED'):<12} {notes_short}"
            )
        print()
        print(
            "Hint: edit data/filters/<brand_id>.yaml to add canonical_handles, "
            "must_have_any, must_have_none, cjk_tokens."
        )
        return 0

    if action == "dry-run":
        from x_monitor.relevance import (
            REASON_CANONICAL_BYPASS,
            REASON_HARD_DROP_NO_SIGNAL,
            REASON_HARD_DROP_URL_ONLY,
            REASON_KEPT,
            REASON_SOFT_DROP_BANNED,
            REASON_URL_ONLY_KEPT,
            filter_posts,
            load_filter,
        )
        # Per-model hardcoded fixture of the kinds of posts that
        # historically hijacked each query (Q1..Q6). The fixture is
        # intentionally compact: 6-8 items per model, mixing real-signal,
        # banned-token, and pure-noise. Purpose: prove the filter
        # decision tree end-to-end without making a real API call.
        fixtures: dict[str, list[dict]] = {
            "moonshot_kimi": [
                {"id": "f1", "text": "Kimi K2 is amazing", "author_handle": "fan"},
                {"id": "f2", "text": "F1 driver Antonelli is fast", "author_handle": "f1fan"},
                {"id": "f3", "text": "F1 qualifying results", "author_handle": "u"},
                {"id": "f4", "text": "hello world", "author_handle": "u"},
                {"id": "f5", "text": "Kimi K2 beats F1 cars in benchmarks", "author_handle": "u"},
                {"id": "f6", "text": "Moonshot AI launched Kimi K2.5", "author_handle": "u"},
                {"id": "f7", "text": "https://t.co/abc", "author_handle": "u"},
            ],
            "inclusionai": [
                {"id": "f1", "text": "Inclusion AI released ring-1t", "author_handle": "fan"},
                {"id": "f2", "text": "Tolkien's theme of inclusion", "author_handle": "u"},
                {"id": "f3", "text": "WWE Raw results Rollins", "author_handle": "u"},
                {"id": "f4", "text": "hello world", "author_handle": "u"},
            ],
            "minimax": [
                {"id": "f1", "text": "minimax M3.0 launch", "author_handle": "fan"},
                {"id": "f2", "text": "hailuo-2.3 prompt guide", "author_handle": "u"},
                {"id": "f3", "text": "celebrity uses hailuo", "author_handle": "u"},
                {"id": "f4", "text": "hello world", "author_handle": "u"},
            ],
            "qwen": [
                {"id": "f1", "text": "Qwen3-Max is great", "author_handle": "fan"},
                {"id": "f2", "text": "hello world", "author_handle": "u"},
            ],
            "deepseek": [
                {"id": "f1", "text": "DeepSeek V3.2 release", "author_handle": "fan"},
                {"id": "f2", "text": "hello world", "author_handle": "u"},
            ],
            "glm": [
                {"id": "f1", "text": "GLM-4.5 launch", "author_handle": "fan"},
                {"id": "f2", "text": "hello world", "author_handle": "u"},
            ],
            "mimo": [
                {"id": "f1", "text": "Xiaomi MiMo v2.5 release", "author_handle": "fan"},
                {"id": "f2", "text": "hello world", "author_handle": "u"},
            ],
        }
        target = args.model if hasattr(args, "model") and args.model else None
        models = [target] if target else sorted(fixtures)
        # Build brand_id -> items list
        for m in models:
            if m not in fixtures:
                print(f"unknown model: {m}", file=sys.stderr)
                continue
            cfg = load_filter(m, paths["data"])
            items = fixtures[m]
            kept, stats, soft = filter_posts(items, cfg)
            print(f"\n[{m}]")
            print(f"  config: canonical={len(cfg.canonical_handles)} "
                  f"must_any={len(cfg.must_have_any)} "
                  f"banned={len(cfg.must_have_none)} "
                  f"drop_url_only={cfg.drop_url_only}")
            print(f"  n_in={len(items)}  n_kept={stats['n_kept']}  "
                  f"n_dropped={stats['n_dropped']}  "
                  f"n_soft_dropped={stats['n_soft_dropped']}")
            print(f"  reasons: {stats['reasons']}")
            if soft:
                print(f"  soft-dropped (review queue):")
                for s in soft:
                    print(f"    - {s['tweet_id']}: {s['text_excerpt']!r}")
        return 0

    if action == "audit-handles":
        from x_monitor.apify import (
            TwitterApiAuthError,
            TwitterApiClient,
            TwitterApiRateLimitError,
            TwitterApiServerError,
        )
        from x_monitor.config import KNOWN_MODELS
        from x_monitor.relevance import (
            load_filter,
            looks_like_ai_account,
        )
        import yaml as _yaml

        # Try to make a real client. If env var is missing, return 2 so the
        # operator can run `x-monitor setup twitterapi-key` first.
        try:
            api = TwitterApiClient.from_env()
        except Exception as e:
            print(
                f"error: {e}\n"
                f"Run `x-monitor setup twitterapi-key` first.\n"
                f"Or set TWITTERAPI_IO_API_KEY in your env.",
                file=sys.stderr,
            )
            return 2

        # Build brand_tokens per model from must_have_any. This is a
        # rough heuristic; canonical_handles is the primary signal.
        brand_tokens_per_model: dict[str, list[str]] = {}
        for m in sorted(KNOWN_MODELS):
            cfg = load_filter(m, paths["data"])
            brand_tokens_per_model[m] = (
                list(cfg.must_have_any)[:3] if cfg.must_have_any else [m]
            )

        print(
            f"{'model':<18} {'handle':<22} {'followers':<10} "
            f"{'verified':<9} {'likely':<7} reason"
        )
        print("-" * 110)

        audited_at = _now_iso_for_audit()
        any_failure = False
        for m in sorted(KNOWN_MODELS):
            cfg = load_filter(m, paths["data"])
            for handle in cfg.canonical_handles:
                try:
                    info = api.user_info(handle)
                except TwitterApiAuthError as e:
                    print(f"  AUTH FAILED: {e}", file=sys.stderr)
                    return 2
                except (TwitterApiRateLimitError, TwitterApiServerError) as e:
                    print(f"  {m}/{handle}: TRANSIENT ERROR {e}", file=sys.stderr)
                    any_failure = True
                    continue
                except Exception as e:
                    print(f"  {m}/{handle}: ERROR {e}", file=sys.stderr)
                    any_failure = True
                    continue
                if not info:
                    print(f"  {m}/{handle:<22} (not found)")
                    continue
                likely, reason = looks_like_ai_account(
                    info, brand_tokens_per_model[m]
                )
                print(
                    f"{m:<18} {handle:<22} "
                    f"{info.get('followers_count', 0):<10} "
                    f"{str(info.get('verified', False)):<9} "
                    f"{str(likely):<7} {reason}"
                )
        print()
        print(
            "Hint: edit data/filters/<model>.yaml to remove handles that look "
            "unrelated, then re-run. Pass --write-verify to stamp "
            "verified_at on all loaded YAMLs."
        )
        if getattr(args, "write_verify", False):
            for m in sorted(KNOWN_MODELS):
                yaml_path = paths["data"] / "filters" / f"{m}.yaml"
                if not yaml_path.exists():
                    continue
                raw = _yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
                raw["verified_at"] = audited_at
                yaml_path.write_text(
                    _yaml.safe_dump(raw, sort_keys=False, allow_unicode=True),
                    encoding="utf-8",
                )
            print(f"\nverified_at updated to {audited_at}")
        return 1 if any_failure else 0

    if action == "backfill":
        from x_monitor.headlines import (
            HeadlinesCache,
            SOURCE_CACHED,
            SOURCE_FETCHED,
            SOURCE_FETCH_FAILED,
            cache_key_for,
            fetch_url,
            is_tco_url,
            resolve_tco,
            x_article_tweet_id,
        )
        from x_monitor.store import Store
        import time as _time

        limit = int(getattr(args, "limit", 200) or 200)
        per_query_cap = int(getattr(args, "batch", 8) or 8)
        skip_throttle = bool(getattr(args, "skip_throttle", False))
        per_host_min_interval = float(
            getattr(args, "per_host_min_interval", 1.0) or 1.0
        )
        via_api = bool(getattr(args, "via_api", False))
        # Build the api client lazily. If --via-api is requested but
        # the env var is missing, we warn and fall back to fetch_url
        # for everything (so the backfill still works for non-X-article
        # URLs).
        api = None
        if via_api:
            try:
                from x_monitor.apify import TwitterApiClient
                api = TwitterApiClient.from_env()
            except Exception as e:
                print(
                    f"warning: --via-api requested but api init failed: {e}\n"
                    f"  falling back to fetch_url for everything.",
                    file=sys.stderr,
                )
                api = None
        via_api_active = via_api and api is not None
        # Open the store (auto-migrates so the new columns exist).
        store = Store(paths["db"], auto_migrate=True)
        try:
            cache = HeadlinesCache(paths["data"] / "headlines_cache.json")
            # First report: what we're about to do.
            total_url_only = store.count_url_only()
            total_headlines = store.count_headlines()
            print(
                f"backfill: {total_url_only} url-only posts, "
                f"{total_headlines} already have headlines, "
                f"limit={limit} per_query_cap={per_query_cap}"
            )
            rows = store.iter_url_only_no_headline(limit=limit)
            if not rows:
                print("nothing to backfill.")
                return 0
            print(f"backfill: processing {len(rows)} posts...")
            stats = {
                "n_total": len(rows),
                "n_already_fresh": 0,
                "n_fetched": 0,
                "n_cached": 0,
                "n_failed": 0,
                "n_skipped": 0,
                "n_via_api": 0,
            }
            fetches_this_run = 0
            host_last_fetch: dict[str, float] = {}
            from urllib.parse import urlparse as _urlparse
            for i, row in enumerate(rows, 1):
                tweet_id = row["tweet_id"]
                url = (row["text"] or "").strip()
                if not url.startswith("http"):
                    stats["n_skipped"] += 1
                    continue
                # Resolve t.co (and similar) redirects. Cache key and
                # fetch target are based on the *resolved* URL.
                fetch_target = url
                if is_tco_url(url):
                    resolved = resolve_tco(url)
                    if resolved:
                        fetch_target = resolved
                # X-article routing: if the resolved URL is an
                # x.com/i/article/{id} and --via-api is on, call
                # api.get_article(tweet_id) using the POST's tweet_id
                # (NOT the article path id — the API rejects that).
                # Cost: 100 credits per call.
                is_x_article = x_article_tweet_id(fetch_target) is not None
                x_tid = tweet_id
                if is_x_article and via_api_active:
                    x_key = f"x_article:{x_tid}"
                    hit = cache.get(x_tid, key_override=x_key)
                    if hit is not None:
                        store.update_post_headline(
                            tweet_id, hit.get("title"), hit["source"]
                        )
                        if hit["source"] == SOURCE_CACHED:
                            stats["n_cached"] += 1
                        else:
                            stats["n_already_fresh"] += 1
                        stats["n_via_api"] = stats.get("n_via_api", 0) + 1
                        continue
                    if fetches_this_run >= limit or fetches_this_run >= per_query_cap * 25:
                        stats["n_skipped"] += 1
                        continue
                    try:
                        article = api.get_article(x_tid)
                    except Exception as e:
                        print(f"  get_article({x_tid}) failed: {e}", file=sys.stderr)
                        article = None
                    fetches_this_run += 1
                    if article is None:
                        cache.put(x_tid, None, SOURCE_FETCH_FAILED, error="api_no_article", key_override=x_key)
                        store.update_post_headline(tweet_id, None, SOURCE_FETCH_FAILED)
                        stats["n_failed"] += 1
                        stats["n_via_api"] = stats.get("n_via_api", 0) + 1
                        continue
                    title = (article.get("title") or "").strip() or None
                    cache.put(x_tid, title, SOURCE_FETCHED, status_code=200, key_override=x_key)
                    source = SOURCE_FETCHED if title else SOURCE_FETCH_FAILED
                    store.update_post_headline(tweet_id, title, source)
                    if title:
                        stats["n_fetched"] += 1
                    else:
                        stats["n_failed"] += 1
                    stats["n_via_api"] = stats.get("n_via_api", 0) + 1
                    if i % 10 == 0 or i == len(rows):
                        print(
                            f"  [{i}/{len(rows)}] fetched={stats['n_fetched']} "
                            f"cached={stats['n_cached']} failed={stats['n_failed']} "
                            f"skipped={stats['n_skipped']} via_api={stats.get('n_via_api', 0)}"
                        )
                    continue
                # Cache check (keyed on resolved URL).
                hit = cache.get(fetch_target)
                if hit is not None:
                    store.update_post_headline(
                        tweet_id, hit.get("title"), hit["source"]
                    )
                    if hit["source"] == SOURCE_CACHED:
                        stats["n_cached"] += 1
                    else:
                        stats["n_already_fresh"] += 1
                    continue
                # Per-host throttle (keyed on resolved host).
                host = (_urlparse(fetch_target).hostname or "").lower()
                now = _time.monotonic()
                if (
                    not skip_throttle
                    and host
                    and host in host_last_fetch
                    and now - host_last_fetch[host] < per_host_min_interval
                ):
                    stats["n_skipped"] += 1
                    continue
                if fetches_this_run >= limit or fetches_this_run >= per_query_cap * 25:
                    # Conservative hard cap on a single backfill run.
                    stats["n_skipped"] += 1
                    continue
                html = fetch_url(fetch_target)
                fetches_this_run += 1
                if host and not skip_throttle:
                    host_last_fetch[host] = _time.monotonic()
                if html is None:
                    cache.put(fetch_target, None, SOURCE_FETCH_FAILED, error="fetch_failed")
                    store.update_post_headline(tweet_id, None, SOURCE_FETCH_FAILED)
                    stats["n_failed"] += 1
                    continue
                from x_monitor.headlines import parse_title
                title = parse_title(html)
                cache.put(fetch_target, title, SOURCE_FETCHED, status_code=200)
                source = SOURCE_FETCHED if title else SOURCE_FETCH_FAILED
                store.update_post_headline(tweet_id, title, source)
                if title:
                    stats["n_fetched"] += 1
                else:
                    stats["n_failed"] += 1
                if i % 10 == 0 or i == len(rows):
                    print(
                        f"  [{i}/{len(rows)}] fetched={stats['n_fetched']} "
                        f"cached={stats['n_cached']} failed={stats['n_failed']} "
                        f"skipped={stats['n_skipped']}"
                    )
            print()
            print("backfill complete:")
            for k, v in stats.items():
                print(f"  {k}: {v}")
            return 0
        finally:
            store.close()

    print(f"unknown relevance action: {action}", file=sys.stderr)
    return 2



def cmd_reattribute(args, paths) -> int:
    """Re-run v1.8 attribution on every post in the DB (Unit 5, R19).

    Walks all rows in  (filtered by --model if supplied) and
    re-runs the v1.8 multi-brand attribution pipeline on each. Writes
    to , , and  via
    Store methods that upsert (ON CONFLICT DO UPDATE). The CLI target
    is the 2,008 historical posts that have empty attribution rows
    after migration 004 dropped .

    Flags:
      --batch-size N   posts per progress-log chunk (default 100)
      --dry-run        do not write; print what would have been written
      --limit N        cap on posts processed (default: all)
      --model BRAND    only reattribute posts attributed to BRAND
                       (joins posts_brands)
      --with-llm       enable per-brand signal classification via
                       Claude Haiku (requires ANTHROPIC_API_KEY in env)

    Returns 0 on success; 2 on config/env errors.
    """
    from x_monitor.reattribute import (
        reattribute_all_posts,
        build_anthropic_client_from_env,
    )

    db_path = paths["db"]
    if not db_path.exists():
        print(f"reattribute: db not found at {db_path}", file=sys.stderr)
        return 2

    anthropic_client = None
    if getattr(args, "with_llm", False):
        anthropic_client = build_anthropic_client_from_env()
        if anthropic_client is None:
            print(
                "reattribute: --with-llm requested but ANTHROPIC_API_KEY "
                "is not set or the anthropic SDK is missing; "
                "running without signal classification",
                file=sys.stderr,
            )

    counts = reattribute_all_posts(
        db_path=db_path,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        limit=args.limit,
        brand_filter=args.model,
        anthropic_client=anthropic_client,
    )
    print(json.dumps(counts, indent=2, ensure_ascii=False))
    return 0


def cmd_translate_posts(args, paths) -> int:
    """Backfill per-locale translation columns on the posts table (U6).

    Plan: docs/plans/2026-07-02-002-feat-streamlined-post-fetch-pipeline-plan.md
    (Unit 6 of 8). Finds posts where `text_en` / `text_zh_cn` /
    `lang_detected` is NULL and runs them through the §5.1
    `translate_batch_pragmatics` (U3) prompt. Writes back via
    `Store.bulk_update_translations` (the v1.7 Store path — the
    row shape is backward-compatible because U3 still populates
    text_en / text_zh_cn / lang_detected alongside the new
    literal_zh / cn_equivalent / annotation prongs). Plan
    2026-07-06-001 dropped `discourse_role` from U3 — pragmatic
    register is exclusively the classifier's per-brand output
    (`posts_brands_discourse`).

    Usage:
        x-monitor translate --locale both --limit 50
        x-monitor translate --locale zh_cn --dry-run
        x-monitor translate --limit 1000

    Flags:
      --locale   en | zh_cn | both (default: both)
      --limit    cap on posts processed (default: 200)
      --dry-run  skip the LLM + DB writes; print the row count only

    Returns 0 on success, 2 on bad args / missing db.
    """
    from x_monitor.store import Store
    from x_monitor.translator import (
        AnthropicClaudeClient,
        translate_batch_pragmatics,
    )

    locale_arg = args.locale
    limit = args.limit
    dry_run = args.dry_run

    if locale_arg == "both":
        target_locales = ["en", "zh_cn"]
    else:
        target_locales = [locale_arg]

    db_path = paths["db"]
    if not db_path.exists():
        print(
            f"translate: db not found at {db_path}",
            file=sys.stderr,
        )
        return 2

    store = Store(db_path, auto_migrate=True)
    try:
        if locale_arg == "both":
            missing_en = store.get_posts_missing_translations(
                "en", limit=limit,
            )
            missing_zh = store.get_posts_missing_translations(
                "zh_cn", limit=limit,
            )
            seen: set[str] = set()
            rows: list[dict] = []
            for r in missing_en + missing_zh:
                pk = str(r["tweet_id"])
                if pk not in seen:
                    seen.add(pk)
                    rows.append({
                        "tweet_id": pk,
                        "text": r.get("text", ""),
                    })
        else:
            missing = store.get_posts_missing_translations(
                locale_arg, limit=limit,
            )
            rows = [
                {"tweet_id": str(r["tweet_id"]),
                 "text": r.get("text", "")}
                for r in missing
            ]

        print(
            f"translate: posts ({len(rows)} rows, locales={target_locales}, "
            f"dry_run={dry_run})"
        )

        if dry_run:
            print(json.dumps({"would_translate": len(rows)}, indent=2))
            return 0

        if not rows:
            print(json.dumps({"translated": 0}, indent=2))
            return 0

        client = AnthropicClaudeClient()
        results = translate_batch_pragmatics(
            rows, target_locales, client,
        )

        update_rows = [
            {
                "tweet_id": r["tweet_id"],
                "text_en": r.get("text_en"),
                "text_zh_cn": r.get("text_zh_cn") or r.get("literal_zh"),
                "lang_detected": r.get("lang_detected"),
            }
            for r in results
        ]
        n_updated = store.bulk_update_translations(update_rows)
        n_failed = sum(1 for r in results if r.get("translation_failed"))
        print(
            json.dumps(
                {
                    "rows_seen": len(rows),
                    "rows_updated": n_updated,
                    "rows_failed": n_failed,
                },
                indent=2,
            )
        )
        return 0
    finally:
        store.close()


def cmd_backfill_unsanctioned_flags(args, paths) -> int:
    """U8b: backfill posts_unsanctioned_flags for recent posts.

    Plan: docs/plans/2026-07-03-003-feat-post-fetch-taxonomy-and-multi-discourse-plan.md
    Unit U8b. Finds posts that have NO `posts_unsanctioned_flags` row
    and runs them through `classify_pragmatics_full` (U2a shape) to
    extract just the top-level `unsanctioned_flags` array. Other prongs
    (post_type / sentiment / discourse / nationalism) are NOT updated
    by this backfill — only the unsanctioned flags.

    Usage:
        x-monitor backfill unsanctioned-flags --limit 200
        x-monitor backfill unsanctioned-flags --limit 500 --yes
        x-monitor backfill unsanctioned-flags --limit 50 --dry-run

    Flags:
      --limit    cap on posts processed (default: 200)
      --dry-run  skip the LLM + DB writes; print the post_ids only
      --yes      required when --limit > 500 (rate-limit protection
                 against accidental large reclassifications)

    Returns 0 on success, 2 on bad args, 1 on --limit > 500 without --yes.
    """
    if args.limit > 500 and not args.yes:
        print(
            f"ERROR: --limit > 500 requires --yes (got --limit={args.limit}). "
            "Refusing to reclassify a large history without explicit "
            "confirmation.",
            file=sys.stderr,
        )
        return 1

    from x_monitor.store import Store
    from x_monitor.attribution import classify_pragmatics_full
    from x_monitor.translator import AnthropicClaudeClient

    db_path = paths["db"]
    if not db_path.exists():
        print(
            f"backfill unsanctioned-flags: db not found at {db_path}",
            file=sys.stderr,
        )
        return 2

    store = Store(db_path, auto_migrate=True)
    client = AnthropicClaudeClient()

    post_ids = store.recent_posts_unsanctioned_missing(args.limit)
    if not post_ids:
        print(
            f"backfill unsanctioned-flags: no posts missing flags "
            f"(limit={args.limit})"
        )
        store.close()
        return 0

    print(
        f"backfill unsanctioned-flags: {len(post_ids)} posts to process "
        f"(limit={args.limit}, dry_run={args.dry_run})"
    )

    if args.dry_run:
        for pid in post_ids[:10]:
            print(f"  would classify: tweet_id={pid}")
        if len(post_ids) > 10:
            print(f"  ... and {len(post_ids) - 10} more")
        store.close()
        return 0

    n_written = 0
    n_failed = 0
    for i, pid in enumerate(post_ids, 1):
        # U2a: classify_pragmatics_full returns the new shape.
        # We discard everything except unsanctioned_flags.
        try:
            classified = classify_pragmatics_full(
                text=store._conn.execute(
                    "SELECT text FROM posts WHERE tweet_id = ?", (pid,)
                ).fetchone()["text"] or "",
                brand_ids=[],  # brand_ids empty → classifier returns empty by_brand
                brand_registry=store.read_brands(),
                anthropic_client=client,
            )
        except Exception as e:
            logger.warning(
                "backfill unsanctioned-flags: classify failed for "
                "tweet_id=%s: %s", pid, e,
            )
            n_failed += 1
            # Rate-limit: 200ms between LLM calls.
            time.sleep(0.2)
            continue

        flags = (
            classified.get("unsanctioned_flags", [])
            if isinstance(classified, dict) else []
        )
        if flags:
            try:
                store.upsert_unsanctioned_flags(pid, flags)
                n_written += 1
            except Exception as e:
                logger.warning(
                    "backfill unsanctioned-flags: upsert failed for "
                    "tweet_id=%s: %s", pid, e,
                )
                n_failed += 1
        # Rate-limit: 200ms between LLM calls.
        time.sleep(0.2)
        # Progress line every 10 posts.
        if i % 10 == 0:
            print(
                f"  progress: {i}/{len(post_ids)} "
                f"(wrote={n_written}, failed={n_failed})"
            )

    print(
        f"backfill unsanctioned-flags: complete — "
        f"wrote={n_written}, failed={n_failed}, total={len(post_ids)}"
    )
    store.close()
    return 0


def cmd_smoketest(args, paths) -> int:
    """U7 + U6: forward to scripts.post_fetch_smoketest.main.

    The db path comes from `paths["db"]` (the live x_monitoring.db);
    the script's hardcoded `data/x_monitoring.db` is also valid but
    we pass the explicit path for testability.

    Flags:
      --source          latest-cycle (default) | fixture | api-query
      --fixture PATH    JSONL file when --source=fixture
      --query STR       advanced-search string for --source=api-query
      --since DATE      ISO YYYY-MM-DD; injected as 'since:' operator
      --max-pages N     pagination cap (api-query, default 5)
      --max-per-page N  per-page request size (api-query, default 20)
      --api-quiet       suppress client._request_log echo
      --sample N        sample-post eyeball section size (default: 5)
      --strict-budget   exit 1 if total wall-clock exceeds 90s
      --limit N         cap posts processed (default: 200)
    """
    import sys as _sys
    from scripts.post_fetch_smoketest import main as _smoke_main

    argv: list[str] = ["--source", args.source]
    if args.fixture:
        argv.extend(["--fixture", str(args.fixture)])
    if getattr(args, "query", None):
        argv.extend(["--query", args.query])
    if getattr(args, "since", None):
        argv.extend(["--since", args.since])
    if getattr(args, "max_pages", None) is not None:
        argv.extend(["--max-pages", str(args.max_pages)])
    if getattr(args, "max_per_page", None) is not None:
        argv.extend(["--max-per-page", str(args.max_per_page)])
    if getattr(args, "api_quiet", False):
        argv.append("--api-quiet")
    argv.extend(["--sample", str(args.sample)])
    if getattr(args, "strict_budget", False):
        argv.append("--strict-budget")
    argv.extend(["--limit", str(args.limit)])
    # chdir into the project root so the script's hardcoded
    # `data/x_monitoring.db` resolves correctly.
    project_root = paths["db"].parent.parent  # data/ → x-monitoring/
    import os as _os
    _prev_cwd = _os.getcwd()
    try:
        _os.chdir(project_root)
        return _smoke_main(argv)
    finally:
        _os.chdir(_prev_cwd)


def cmd_translate_registry(args, paths) -> int:
    """Backfill per-locale columns on registry tables (Unit 4).

    Translates the source column on `brands` / `companies` / `accounts`
    into en + zh-CN via Claude Haiku 4.5 and writes back via
    `Store.bulk_update_registry_translations`. Idempotent (only fills
    rows where the target column is NULL).

    Usage:
        x-monitor translate-registry brands display_name --locale both
        x-monitor translate-registry accounts bio --locale zh_cn --limit 50
        x-monitor translate-registry companies display_name --dry-run

    Flags:
      --locale   en | zh_cn | both (default: both)
      --limit    cap on rows processed (default: 200)
      --dry-run  skip the LLM + DB writes; just print the row count
    """
    from x_monitor.store import Store
    from x_monitor.translator import (
        AnthropicClaudeClient,
        translate_registry_rows,
    )

    table = args.table
    column = args.column
    locale_arg = args.locale
    limit = args.limit
    dry_run = args.dry_run

    # Guard: bio is only on accounts.
    if column == "bio" and table != "accounts":
        print(
            f"translate-registry: column='bio' is only valid for "
            f"table='accounts', got table={table!r}",
            file=sys.stderr,
        )
        return 2

    if locale_arg == "both":
        target_locales = ["en", "zh_cn"]
    else:
        target_locales = [locale_arg]

    db_path = paths["db"]
    if not db_path.exists():
        print(
            f"translate-registry: db not found at {db_path}",
            file=sys.stderr,
        )
        return 2

    store = Store(db_path, auto_migrate=True)
    try:
        # Find rows needing translation per target locale. For "both",
        # we union across locales (a row needs translation if EITHER
        # locale column is NULL).
        if locale_arg == "both":
            missing_en = store.get_registry_missing_translations(
                table, column, "en", limit=limit,
            )
            missing_zh = store.get_registry_missing_translations(
                table, column, "zh_cn", limit=limit,
            )
            seen: set[str] = set()
            rows = []
            for r in missing_en + missing_zh:
                pk = str(r["pk"])
                if pk not in seen:
                    seen.add(pk)
                    rows.append({"pk": pk, "source": r["source"]})
        else:
            missing = store.get_registry_missing_translations(
                table, column, locale_arg, limit=limit,
            )
            rows = [{"pk": str(r["pk"]), "source": r["source"]} for r in missing]

        print(
            f"translate-registry: {table}.{column} "
            f"({len(rows)} rows, locales={target_locales}, "
            f"dry_run={dry_run})"
        )

        if dry_run:
            print(json.dumps({"would_translate": len(rows)}, indent=2))
            return 0

        if not rows:
            print(json.dumps({"translated": 0}, indent=2))
            return 0

        # Build the column_label for the prompt context.
        column_label = f"{table.rstrip('s')} {column.replace('_', ' ')}"

        client = AnthropicClaudeClient()
        results = translate_registry_rows(
            rows, target_locales, client,
            column_label=column_label,
        )

        # Write back via Store. Drop dry_run / translation_failed flags.
        update_rows = [
            {
                "pk": r["pk"],
                "col_en": r.get("col_en"),
                "col_zh_cn": r.get("col_zh_cn"),
            }
            for r in results
        ]
        n_updated = store.bulk_update_registry_translations(
            table, column, update_rows,
        )
        n_failed = sum(1 for r in results if r.get("translation_failed"))
        print(
            json.dumps(
                {
                    "rows_seen": len(rows),
                    "rows_updated": n_updated,
                    "rows_failed": n_failed,
                },
                indent=2,
            )
        )
        return 0
    finally:
        store.close()


def cmd_hf_products(args, paths) -> int:
    """Collect HuggingFace models for each enabled company into `products`.

    Flags:
      --companies a,b   comma-separated company_ids or display names (default: all)
      --brand BRAND     single company_id / display name (alias for --companies)
      --max N           cap models per org
      --dry-run         resolve orgs only; write nothing

    The outer loop iterates companies (corporate parent), then for each
    company iterates its HF orgs (1:N) and brands (M:N). Products are
    attributed to the company’s brands via the brands_companies edge.
    Discovery is automatic: companies lacking a confirmed HF org are
    searched and their candidates are persisted flagged for review (not
    scraped this run). HF auth uses HF_TOKEN from the environment
    (anonymous if unset).
    """
    from x_monitor import hf_products
    from x_monitor.store import Store

    store = Store(paths["db"], auto_migrate=True)
    try:
        companies = None
        if args.companies:
            companies = [c.strip() for c in args.companies.split(",") if c.strip()]
        elif args.brand:
            companies = [args.brand]

        results = hf_products.collect_all(
            store,
            companies=companies,
            max=args.max,
            dry_run=args.dry_run,
        )
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return 0
    finally:
        store.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="x-monitor", description="x-monitor CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run the daily harvest")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--models", help="comma-separated brand_id filter")
    p_run.add_argument("--queries", help="comma-separated query_id filter (Q1..Q6)")
    p_run.set_defaults(func=cmd_run)

    p_dr = sub.add_parser("dry-run", help="Alias for `run --dry-run`")
    p_dr.add_argument("--models", help="comma-separated brand_id filter")
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

    p_rel = sub.add_parser(
        "relevance",
        help="Per-model relevance filter operations (v1.2)",
    )
    p_rel.add_argument(
        "relevance_action",
        choices=["list", "dry-run", "audit-handles", "backfill"],
    )
    p_rel.add_argument(
        "--model",
        help="Restrict dry-run to one model (default: all)",
    )
    p_rel.add_argument(
        "--limit", type=int, default=200,
        help="Max posts to process in a single backfill run (default: 200)",
    )
    p_rel.add_argument(
        "--batch", type=int, default=8,
        help="Per-backfill cap equivalent to per-query cap (default: 8)",
    )
    p_rel.add_argument(
        "--skip-throttle",
        action="store_true",
        help="Disable per-host throttle in backfill (use with care; "
             "may hammer a single origin)",
    )
    p_rel.add_argument(
        "--per-host-min-interval",
        type=float,
        default=1.0,
        help="Minimum seconds between fetches to the same host "
             "(default: 1.0; ignored if --skip-throttle is set)",
    )
    p_rel.add_argument(
        "--via-api",
        action="store_true",
        help="Use TwitterAPI.io get_article() for x.com/i/article URLs "
             "(100 credits per call). Requires TWITTERAPI_IO_API_KEY in env.",
    )
    p_rel.add_argument(
        "--write-verify",
        action="store_true",
        help="Stamp verified_at on data/filters/<model>.yaml after audit-handles",
    )
    p_rel.set_defaults(func=cmd_relevance)

    p_reatt = sub.add_parser(
        "reattribute",
        help="Re-run v1.8 attribution on every post in the DB (Unit 5)",
    )
    p_reatt.add_argument(
        "--batch-size", type=int, default=100,
        help="Posts per progress-log chunk (default: 100)",
    )
    p_reatt.add_argument(
        "--dry-run", action="store_true",
        help="Do not write; print what would have been written",
    )
    p_reatt.add_argument(
        "--limit", type=int, default=None,
        help="Cap on posts processed (default: all)",
    )
    p_reatt.add_argument(
        "--model", dest="model", default=None,
        help="Only reattribute posts attributed to this brand_id "
             "(joins posts_brands)",
    )
    p_reatt.add_argument(
        "--with-llm", action="store_true",
        help="Enable per-brand signal classification via Claude Haiku "
             "(requires ANTHROPIC_API_KEY in env)",
    )
    p_reatt.set_defaults(func=cmd_reattribute)

    p_tr = sub.add_parser(
        "translate-registry",
        help="Backfill per-locale columns on registry tables (Unit 4)",
    )
    p_tr.add_argument(
        "table", choices=["brands", "companies", "accounts"],
        help="Registry table to translate.",
    )
    p_tr.add_argument(
        "column", choices=["display_name", "bio"],
        help="Column to translate. 'bio' is only valid for table='accounts'.",
    )
    p_tr.add_argument(
        "--locale", choices=["en", "zh_cn", "both"], default="both",
        help="Target locale(s). Default 'both'.",
    )
    p_tr.add_argument(
        "--limit", type=int, default=200,
        help="Cap on rows processed (default: 200).",
    )
    p_tr.add_argument(
        "--dry-run", action="store_true",
        help="Skip the LLM and DB writes; print the row count only.",
    )
    p_tr.set_defaults(func=cmd_translate_registry)

    p_tp = sub.add_parser(
        "translate",
        help="Backfill per-locale translation columns on the posts table (U6)",
    )
    p_tp.add_argument(
        "--locale", choices=["en", "zh_cn", "both"], default="both",
        help="Target locale(s). Default 'both'.",
    )
    p_tp.add_argument(
        "--limit", type=int, default=200,
        help="Cap on posts processed (default: 200).",
    )
    p_tp.add_argument(
        "--dry-run", action="store_true",
        help="Skip the LLM and DB writes; print the row count only.",
    )
    p_tp.set_defaults(func=cmd_translate_posts)

    p_smoke = sub.add_parser(
        "smoketest",
        help="One-cycle post-fetch smoketest (U7): run the entire "
             "pipeline on the latest cycle's kept posts and print a "
             "report (per-stage counts, timing, sample posts, errors).",
    )
    p_smoke.add_argument(
        "--source",
        choices=["latest-cycle", "fixture", "api-query"],
        default="latest-cycle",
    )
    p_smoke.add_argument(
        "--fixture", type=Path, default=None,
    )
    p_smoke.add_argument(
        "--query",
        help="Advanced-search string for --source=api-query (X "
             "operators; costs real TwitterAPI.io quota).",
    )
    p_smoke.add_argument(
        "--since",
        help="ISO date YYYY-MM-DD; injected as 'since:' operator "
             "for --source=api-query.",
    )
    p_smoke.add_argument(
        "--max-pages", type=int, default=5,
        help="Pagination depth cap for --source=api-query (default: 5).",
    )
    p_smoke.add_argument(
        "--max-per-page", type=int, default=20,
        help="Per-page request size for --source=api-query (default: 20).",
    )
    p_smoke.add_argument(
        "--api-quiet", action="store_true",
        help="Suppress client._request_log echo for --source=api-query.",
    )
    p_smoke.add_argument(
        "--sample", type=int, default=5,
    )
    p_smoke.add_argument(
        "--strict-budget", action="store_true",
        help="Exit 1 if total wall-clock exceeds 90s.",
    )
    p_smoke.add_argument(
        "--limit", type=int, default=200,
    )
    p_smoke.set_defaults(func=cmd_smoketest)

    p_bu = sub.add_parser(
        "backfill",
        help="Backfill commands (selective reclassification)",
    )
    p_bu_sub = p_bu.add_subparsers(dest="backfill_cmd", required=True)
    p_bu_uf = p_bu_sub.add_parser(
        "unsanctioned-flags",
        help="Backfill posts_unsanctioned_flags for recent posts (U8b)",
    )
    p_bu_uf.add_argument(
        "--limit", type=int, default=200,
        help="Cap on posts to process (default: 200).",
    )
    p_bu_uf.add_argument(
        "--dry-run", action="store_true",
        help="Skip the LLM + DB writes; print the post_ids only.",
    )
    p_bu_uf.add_argument(
        "--yes", action="store_true",
        help="Required when --limit > 500 (prevents accidental large "
             "reclassifications).",
    )
    p_bu_uf.set_defaults(func=cmd_backfill_unsanctioned_flags)

    p_hf = sub.add_parser(
        "hf-products",
        help="Collect HuggingFace models per brand into the products table",
    )
    p_hf.add_argument(
        "--companies",
        help="comma-separated brand_ids or display names (default: all)",
    )
    p_hf.add_argument("--brand", help="single brand_id / display name")
    p_hf.add_argument("--max", type=int, default=None, help="cap models per org")
    p_hf.add_argument(
        "--dry-run", action="store_true", help="resolve orgs only; write nothing"
    )
    p_hf.set_defaults(func=cmd_hf_products)

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
