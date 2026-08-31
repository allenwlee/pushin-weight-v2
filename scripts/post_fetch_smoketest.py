# {{AGENT_ATTRIBUTION}}
"""U7: one-cycle post-fetch smoketest runner.

Plan: docs/plans/2026-07-02-002-feat-streamlined-post-fetch-pipeline-plan.md
(Unit 7 of 8). Exercises the entire post-fetch pipeline (U3
translate + U4 classify) against either the most recent cycle's
kept posts OR a fixture file, and prints:

  - counts per stage (n_classified, n_translated, n_discourse,
    n_nationalism)
  - per-stage timing in milliseconds
  - 5 sample posts with all annotation fields aligned for
    eyeball coherence (text + text_en + literal_zh +
    cn_equivalent + china_nationalism + us_nationalism +
    per-brand discourse_role)
  - error report grouped by stage (LLM failures, parse failures,
    missing brand attribution)
  - exit code: 0 always; --strict-budget exits 1 if cycle-time
    exceeded the 90s ceiling

Two entry points:
  - `python -m scripts.post_fetch_smoketest [flags]`
  - `x-monitor smoketest [flags]` (after install)
  - `LaunchAgent deploy --smoketest` (operational gate)

This is the user-facing one-cycle-test-and-examine artifact —
the hard requirement from the plan's user brief.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Repo-relative imports — `x_monitor` is the package on sys.path
# when invoked via `python -m scripts.post_fetch_smoketest` from
# the x-monitoring/ project root.


def _print_call_preview() -> None:
    """Print the planned per-cycle TwitterAPI calls to stderr.

    Used by the `--include-call-preview` smoketest flag. Loads
    `config.yaml::x_query_specs` and the live DB's primary keyword
    subset, then renders every spec via `_build_query` / `plan_calls`
    and prints each line as `CALL <id>: <query_string> | <n> chars`.

    No TwitterAPI calls are made. The DB is opened only to load
    `brand_keywords.is_primary=1` for the wide-net specs (B1/B2/B3);
    if the DB is missing, the wide-net specs are rendered with
    empty tokens (their unions become empty parens — the operator
    sees the empty-paren defensive branch and knows to migrate).
    """
    from x_monitor.config import load_config
    from x_monitor.query_plan import plan_calls
    from x_monitor.store import Store

    cfg = load_config(Path("config.yaml"))
    db_path = Path("data") / "x_monitoring.db"
    primary_keywords: dict[str, list[str]] = {}
    if db_path.exists():
        s = Store(db_path, auto_migrate=False)
        try:
            primary_keywords = s.read_primary_brand_keywords()
        finally:
            s.close()

    try:
        calls = plan_calls(
            cfg.x_monitor_list_id, cfg.x_query_specs,
            primary_keywords=primary_keywords,
        )
    except Exception as exc:
        print(f"call-preview: planner raised {exc!r}", file=sys.stderr)
        return

    print("CALL PREVIEW (per-cycle TwitterAPI plan):", file=sys.stderr)
    for c in calls:
        print(
            f"CALL {c.call_id}: {c.query_string} | {c.query_length} chars",
            file=sys.stderr,
        )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="post_fetch_smoketest",
        description="Run the post-fetch pipeline once and print results",
    )
    p.add_argument(
        "--source",
        choices=["latest-cycle", "latest-n", "fixture", "api-query"],
        default="latest-cycle",
        help="Where to source the kept posts from (default: latest-cycle). "
             "'latest-n' pulls the N most recent prod posts with no brand "
             "filter. 'api-query' costs real TwitterAPI.io quota — opt-in.",
    )
    p.add_argument(
        "--fixture",
        type=Path,
        help="JSONL fixture file of {tweet_id, text, attributed_brands}. "
             "Required when --source=fixture.",
    )
    query_group = p.add_mutually_exclusive_group()
    query_group.add_argument(
        "--query",
        help="Advanced-search string (X operators). Required when "
             "--source=api-query. e.g. 'kimi K2.7 lang:en min_faves:5'",
    )
    # Plan 2026-07-11-001 (U4): --query-from-yaml is RETIRED. The
    # per-brand yamls in data/queries/ are gone; the only operator-
    # facing source for a query string is the inline --query flag or
    # the `x_query_specs[*].rendered` precomputation in config.
    p.add_argument(
        "--query-id", default=None,
        help="Reserved for future spec-id selection (currently unused).",
    )
    p.add_argument(
        "--since",
        help="ISO date YYYY-MM-DD; injected as 'since:' operator if "
             "not already in --query.",
    )
    p.add_argument(
        "--max-pages", type=int, default=5,
        help="Pagination depth cap for --source=api-query "
             "(default: 5).",
    )
    p.add_argument(
        "--max-per-page", type=int, default=20,
        help="Per-page request size for --source=api-query "
             "(default: 20, the platform cap).",
    )
    p.add_argument(
        "--api-quiet", action="store_true",
        help="Suppress client._request_log echo for --source=api-query.",
    )
    p.add_argument(
        "--sample", type=int, default=5,
        help="Number of sample posts to render in the eyeball section "
             "(default: 5).",
    )
    p.add_argument(
        "--strict-budget", action="store_true",
        help="Exit with code 1 if total wall-clock exceeds 90s.",
    )
    p.add_argument(
        "--limit", type=int, default=200,
        help="Cap on posts processed for --source=latest-cycle and "
             "--source=api-query (default: 200).",
    )
    p.add_argument(
        "--latest", type=int, default=20,
        help="Cap on posts for --source=latest-n (default: 20). "
             "Distinct from --limit, which caps --source=latest-cycle and "
             "--source=api-query.",
    )
    p.add_argument(
        "--include-call-preview", action="store_true",
        help="Print the planned per-cycle TwitterAPI calls (from "
             "`x_query_specs:`) to stderr, including each call's "
             "rendered query string and character length. Operators "
             "use this to eyeball the v2 B1/B2/B3 fan-out without "
             "hitting TwitterAPI. Default off so existing smoketest "
             "output is unchanged.",
    )
    p.add_argument(
        "--include-all-list-posts", action="store_true",
        help="Skip the brand-keyword filter for --source=api-query. "
             "Used for Call A (list-based fan-in) where the list is "
             "pre-curated and the value signal is who said it (staff "
             "vs. personal), not whether a brand keyword appears in "
             "the text. Posts with no detected brand attribution are "
             "still rendered with `types=(none)` and the brand is "
             "inferred from the role annotation (official|staff|"
             "community|none). Default off so existing behavior is "
             "unchanged.",
    )
    return p.parse_args(argv)


def _load_latest_cycle_posts(
    store, anthropic_client, limit: int
) -> tuple[list[dict], int]:
    """Pull the most recent kept posts from the DB and use the
    deterministic brand-keyword detector to assign brand_ids.

    The classifier must NEVER rely on `posts_brands.brand_id`
    alone — that table was populated by the noisy body-keyword
    scan (e.g. Spanish "llama" matches as a verb get attributed
    to the llama brand). For the post-fetch classifier we want
    the same keyword machinery the LLM is told to trust, applied
    deterministically to the post text.

    Returns:
        (posts, posts_with_no_brand_skipped) — the filtered list
        of posts with at least one monitored-brand attribution,
        plus the count of posts that were excluded because none
        of the 5 monitored brands was detected.
    """
    from x_monitor.attribution import (
        compile_keyword_index,
        detect_brand_mentions,
    )
    # Build the keyword index from the live `brand_keywords` table.
    brand_keywords = store.read_brand_keywords()
    compiled_index = compile_keyword_index(brand_keywords)

    rows = store._conn.execute(
        """
        SELECT p.tweet_id, p.text, p.lang_detected, p.author_handle
        FROM posts p
        ORDER BY p.fetched_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        text = r["text"] or ""
        # Deterministic brand detection: text-scan the same regex
        # index the original attribution used, but treat its
        # output as the GROUND TRUTH for the classifier (not the
        # noisy posts_brands table).
        brand_ids = detect_brand_mentions(text, compiled_index)
        out.append({
            "tweet_id": r["tweet_id"],
            "id": r["tweet_id"],
            "text": text,
            "lang_detected": r["lang_detected"],
            "author_handle": r["author_handle"] if "author_handle" in r.keys() else None,
            "brand_id": brand_ids[0] if brand_ids else "",
            "brand_ids": brand_ids,
        })
    # U5: filter out posts with no monitored-brand attribution.
    # Posts with empty `brand_ids` get the LLM budget skipped — the
    # classifier needs a brand list to attach classifications to.
    filtered = [p for p in out if p.get("brand_ids")]
    skipped = len(out) - len(filtered)
    return filtered, skipped


def _load_fixture_posts(path: Path) -> list[dict]:
    """Read a JSONL fixture file. Each line: {tweet_id, text,
    attributed_brands: [brand_id, ...]}."""
    out: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            out.append({
                "tweet_id": str(row["tweet_id"]),
                "id": str(row["tweet_id"]),
                "text": row.get("text", ""),
                "lang_detected": row.get("lang_detected"),
                "author_handle": row.get("author_handle"),
                "brand_id": (row.get("attributed_brands") or [""])[0],
                "brand_ids": row.get("attributed_brands") or [],
            })
    return out


def _load_latest_n_posts(
    store, limit: int
) -> tuple[list[dict], int]:
    """Pull the N most recent posts from the DB for --source=latest-n.

    Mirrors `_load_latest_cycle_posts` (same row shape, same brand-keyword
    detection) but with two differences:
    - SQL lives in `Store.read_recent_posts(limit)` (not inline).
    - No no-brand filter: posts with empty `brand_ids` are still returned
      so the operator can see the full raw upstream ingest. The renderer
      already handles empty `brand_ids` (renders `post:` block with
      `types=(none)` and `brand_mentions: (none)`).

    Returns:
        (posts, posts_with_no_brand_skipped) — the full post list
        (no skips) and 0 (this mode does not skip).
    """
    from x_monitor.attribution import (
        compile_keyword_index,
        detect_brand_mentions,
    )
    # Build the keyword index from the live `brand_keywords` table —
    # same machinery the classifier is told to trust, applied to the
    # post text.
    brand_keywords = store.read_brand_keywords()
    compiled_index = compile_keyword_index(brand_keywords)

    rows = store.read_recent_posts(limit)
    out: list[dict] = []
    for r in rows:
        text = r["text"] or ""
        brand_ids = detect_brand_mentions(text, compiled_index)
        out.append({
            "tweet_id": r["tweet_id"],
            "id": r["tweet_id"],
            "text": text,
            "lang_detected": r["lang_detected"],
            "author_handle": r.get("author_handle"),
            "brand_id": brand_ids[0] if brand_ids else "",
            "brand_ids": brand_ids,
        })
    return out, 0



def _load_api_posts(
    args,
    compiled_index,
) -> tuple[list[dict], int]:
    """U6: Fetch posts live from the TwitterAPI.io / Apify client and
    apply the same brand-keyword detector that the DB path uses.

    Costs real API quota — opt-in via --source=api-query. Returns the
    filtered (posts, posts_with_no_brand_skipped) tuple, mirroring
    `_load_latest_cycle_posts`.
    """
    # Lazy import — the live client is only needed on this path.
    from x_monitor.apify import TwitterApiClient
    from x_monitor.attribution import detect_brand_mentions
    from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose

    # Explicit smoke tests are on-demand work and must not consume the
    # scheduled collection credential.
    client = TwitterApiClient.from_env(TwitterApiCredentialPurpose.ON_DEMAND)
    rows = client.run_search(
        query=args.query,
        max_results=args.limit,
        since=args.since,
        max_pages=args.max_pages,
        max_per_page=args.max_per_page,
    )

    if not getattr(args, "api_quiet", False):
        print(
            f"smoketest: api-query '{args.query}' returned "
            f"{len(rows)} posts",
            file=sys.stderr,
        )

    out: list[dict] = []
    for r in rows:
        # TwitterAPI.io / Apify rows come back with shapes that vary
        # by vendor; map the common fields defensively.
        tweet_id = str(r.get("tweet_id") or r.get("id") or "")
        text = r.get("text") or r.get("full_text") or ""
        author_handle = (
            r.get("author_handle")
            or (r.get("user") or {}).get("screen_name")
            or (r.get("user") or {}).get("username")
        )
        lang = r.get("lang_detected") or r.get("lang")
        brand_ids = detect_brand_mentions(text, compiled_index)
        out.append({
            "tweet_id": tweet_id,
            "id": tweet_id,
            "text": text,
            "lang_detected": lang,
            "author_handle": author_handle,
            "brand_id": brand_ids[0] if brand_ids else "",
            "brand_ids": brand_ids,
        })
    filtered = [p for p in out if p.get("brand_ids")]
    skipped = len(out) - len(filtered)
    # --include-all-list-posts: keep list-member posts whose text did
    # not trigger a brand-keyword match. Used for Call A where the
    # value signal is the handle/role, not brand text. Posts with
    # empty brand_ids stay in the list; classification stage will
    # skip them (`if not brand_ids: continue`) but the renderer will
    # still show them with `types=(none)` so the operator can see
    # the raw return.
    if getattr(args, "include_all_list_posts", False):
        return out, 0
    return filtered, skipped


def _load_handle_roles(store, handles: list[str]) -> dict[str, str]:
    """For each handle in `handles`, look up the highest-rank role
    (official > staff > community, by MIN(role_id)) the handle
    currently holds in `brands_accounts`. Returns {handle:
    "official"|"staff"|"community"}.

    Used by the smoketest renderer to annotate list-member posts
    with their DB-canonical role so the operator can eyeball the
    "official/staff news vs. personal take" split for Call A. Only
    handles with a role match appear in the result; the caller
    should default to "none" for any handle not present.
    """
    if not handles:
        return {}
    placeholders = ",".join("?" for _ in handles)
    sql = (
        "SELECT a.handle AS handle, r.key AS role_key "
        "FROM accounts a "
        "JOIN brands_accounts ba ON ba.accounts_id = a.id "
        "JOIN roles r ON r.id = ba.role_id "
        f"WHERE a.handle IN ({placeholders}) "
        "GROUP BY a.handle "
        "ORDER BY MIN(ba.role_id) ASC"
    )
    rows = store._conn.execute(sql, tuple(handles)).fetchall()
    return {r["handle"]: r["role_key"] for r in rows}


def _render_sample_posts(
    sample_posts: list[dict],
    translation_rows: list[dict],
    classification_rows: dict[str, list[dict]],
    unsanctioned_flags: dict[str, list[str]] | None = None,
    role_by_handle: dict[str, str] | None = None,
) -> str:
    """Render N posts with translator + classifier fields aligned.

    Layout (smoketest skill 2026-07-06, hierarchical):
        post:
          types=<unique post_types across all brands>
          annotation=<translator-emitted annotation>
        brand_mentions:
          <brand_id>
            post_types:
              - <value>
            sentiment=<value>
            cls_discourse=<value|omitted>
            cn=<value>
            us=<value>

    U1-final (plan 2026-07-06-001): discourse_role is classifier-only.
    The translator's post-level `discourse_role` was REMOVED from the
    contract — pragmatic register is exclusively the per-brand
    classifier output, persisted to `posts_brands_discourse`. So
    `trans_disc:` is no longer rendered; `cls_disc=` is the only
    discourse field per brand.

    U2 (plan 2026-07-04): each post header includes the full X / Twitter
    URL `https://x.com/<handle>/status/<tweet_id>` (or `(no handle)`
    fallback) so reviewers can click through without copy-pasting the
    tweet_id.

    `unsanctioned_flags` is an optional per-post_id list of flag values
    that get surfaced in a dedicated section at the end.
    """
    unsanctioned_flags = unsanctioned_flags or {}
    role_by_handle = role_by_handle or {}
    trans_by_id = {r["tweet_id"]: r for r in translation_rows}
    lines: list[str] = []
    lines.append("")
    lines.append("=== SAMPLE POSTS ===")
    for i, post in enumerate(sample_posts, 1):
        tid = str(post.get("tweet_id") or post.get("id"))
        # U2: build the URL line. Handle may be None / empty for some
        # posts (older fixtures, no-handle apify responses); fall back
        # to "(no handle)" so the URL slot is unambiguous.
        handle = post.get("author_handle") or "(no handle)"
        lines.append(
            f"--- Post {i} (tweet_id={tid} "
            f"url=https://x.com/{handle}/status/{tid}) ---"
        )
        # Role annotation (smoketest --include-all-list-posts):
        # surfaces the DB-canonical role (official/staff/community)
        # for the author handle so the operator can eyeball the
        # "official news vs. personal take" split for Call A. Only
        # emitted when caller passed a non-empty role_by_handle map.
        if role_by_handle:
            role = role_by_handle.get(handle, "none") if handle != "(no handle)" else "none"
            lines.append(f"role:        {role}")
        lines.append(f"text:        {post.get('text', '')}")
        tr = trans_by_id.get(tid, {})
        lines.append(f"text_en:     {(tr.get('text_en') or '')}")
        lines.append(f"literal_zh:  {(tr.get('literal_zh') or tr.get('text_zh_cn') or '')}")
        # No trans_disc — translator no longer emits discourse_role.
        lines.append(f"cn_equiv:    {(tr.get('cn_equivalent') or '')}")
        # U7: per-post unsanctioned flags (if any).
        flags = unsanctioned_flags.get(tid, [])
        if flags:
            lines.append(f"unsanctioned: {','.join(flags)}")
        # Hierarchical layout (smoketest skill 2026-07-06).
        # post: block groups post-level tags (types, annotation);
        # brand_mentions: block groups per-brand tags with the brand
        # name as a bare section header. Multi-value post_types /
        # discourse_roles render as nested bullets, not flattened.
        brand_rows = classification_rows.get(tid, [])
        all_post_types: list[str] = []
        for cls in brand_rows:
            post_types = cls.get("post_types") or (
                [cls["post_type"]] if cls.get("post_type") else []
            )
            for pt in post_types:
                if pt and pt not in all_post_types:
                    all_post_types.append(pt)
        # --- post: ----------------------------------------------------
        if not brand_rows:
            lines.append("post:")
            lines.append("  types=(none)")
            lines.append(f"  annotation={tr.get('annotation') or '(none)'}")
            lines.append("brand_mentions: (none)")
            continue
        lines.append("post:")
        if all_post_types:
            lines.append(f"  types={','.join(all_post_types)}")
        else:
            lines.append("  types=(none)")
        lines.append(f"  annotation={tr.get('annotation') or '(none)'}")
        # --- brand_mentions: -----------------------------------------
        lines.append("brand_mentions:")
        for cls in brand_rows:
            brand_id = cls["brand_id"]
            lines.append(f"  {brand_id}")
            # post_types — bullet list when array, single line for
            # legacy scalar (still keeping the key=`post_types=` name
            # for forward-compat with the array shape).
            post_types = cls.get("post_types")
            if post_types is None:
                scalar = cls.get("post_type")
                if scalar:
                    lines.append(f"    post_types={scalar}")
            else:
                lines.append("    post_types:")
                for pt in post_types:
                    lines.append(f"      - {pt}")
            lines.append(f"    sentiment={cls['sentiment']}")
            # discourse_roles — single `cls_discourse=` line for one
            # element; nested bullets for many; omit entirely when
            # both arrays are absent. Prefer the modern `discourse_roles`
            # array; fall back to legacy scalar `discourse_role`.
            has_array = "discourse_roles" in cls
            raw_drs = cls.get("discourse_roles")
            legacy_dr = cls.get("discourse_role")
            if has_array and raw_drs:
                if len(raw_drs) == 1:
                    lines.append(f"    cls_discourse={raw_drs[0]}")
                else:
                    lines.append("    discourse_roles:")
                    for dr in raw_drs:
                        lines.append(f"      - {dr}")
                    # No `cls_discourse=` line in the multi-bullet case.
            elif legacy_dr:
                lines.append(f"    cls_discourse={legacy_dr}")
            lines.append(f"    cn={cls['china_nationalism']}")
            lines.append(f"    us={cls['us_nationalism']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.source == "fixture" and not args.fixture:
        print(
            "--source=fixture requires --fixture PATH",
            file=sys.stderr,
        )
        return 2
    if args.source == "api-query" and not args.query:
        print(
            "--source=api-query requires --query '...' (advanced-search string)",
            file=sys.stderr,
        )
        return 2
    if args.fixture and not args.fixture.exists():
        print(f"--fixture not found: {args.fixture}", file=sys.stderr)
        return 2
    if args.source == "latest-n" and args.latest <= 0:
        print(
            f"--latest must be > 0 (got {args.latest})",
            file=sys.stderr,
        )
        return 2
    if args.latest > args.limit:
        print(
            f"WARNING: --latest {args.latest} exceeds --limit {args.limit}; "
            f"clamping --latest to {args.limit}",
            file=sys.stderr,
        )
        args.latest = args.limit

    # Plan 2026-07-11-002 (U3): when --include-call-preview is set,
    # print the planned per-cycle TwitterAPI calls (from
    # `x_query_specs:`) to stderr. Each line shows the call_id,
    # rendered query string, and query_length. Operators use this
    # to eyeball the B1/B2/B3 fan-out without hitting TwitterAPI.
    # The DB is opened only to load `brand_keywords.is_primary=1`
    # for the wide-net specs; if the DB is missing and the call
    # set has no wide-net specs, the preview still works.
    if args.include_call_preview:
        _print_call_preview()
        # Continue into the normal dispatch — preview is a side
        # channel, not a replacement for the source-mode pipeline.
    # Plan 2026-07-11-001 (U4): --query-from-yaml is removed. The
    # smoketest's --source=api-query path requires the operator to
    # pass --query <string> directly. Per-brand yamls in data/queries/
    # are gone.

    from x_monitor.store import Store
    from x_monitor.translator import (
        AnthropicClaudeClient,
        translate_batch_pragmatics,
    )
    from x_monitor.attribution import classify_pragmatics_full

    # Lazy import so the smoke test can run on a workstation
    # without the db schema being initialized (the LaunchAgent
    # caller creates the db first; offline `--dry-run` paths
    # accept an empty store).
    #
    # --source=fixture and --source=api-query bypass the DB entirely;
    # only --source=latest-cycle and --source=latest-n require a DB on disk.

    if args.source == "fixture":
        # Fixture path was validated by argparse (existence + path).
        # Run the pipeline in-memory; no DB on disk is touched.
        posts = _load_fixture_posts(args.fixture)
        brand_registry_rows = []
        return _run_pipeline(posts, brand_registry_rows, args)

    if args.source == "api-query":
        # api-query still needs the DB to load brand keywords (the
        # canonical keyword list lives in the brand_keywords table).
        # Tests inject a fake via monkeypatch on the api-query helper.
        from x_monitor.attribution import compile_keyword_index
        db_path = Path("data") / "x_monitoring.db"
        if not db_path.exists():
            print(
                f"smoketest: --source=api-query needs the DB at {db_path} "
                "to load brand keywords (run a cycle first).",
                file=sys.stderr,
            )
            return 2
        store = Store(db_path, auto_migrate=True)
        try:
            brand_keywords = store.read_brand_keywords()
            brand_registry_rows = store.read_brands()
            compiled_index = compile_keyword_index(brand_keywords)
            posts, posts_with_no_brand_skipped = _load_api_posts(
                args, compiled_index
            )
            # Pass the open store to _run_pipeline so it can resolve
            # per-handle roles from brands_accounts (Call A's
            # "official/staff news vs. personal take" annotation).
            args._role_lookup_store = store
            return _run_pipeline(
                posts, brand_registry_rows, args,
                posts_with_no_brand_skipped=posts_with_no_brand_skipped,
            )
        finally:
            store.close()

    if args.source == "latest-n":
        # Mirrors the api-query branch: opens Store, builds the brand
        # keyword index for the renderer's `brand_mentions:` block, then
        # dispatches `_run_pipeline`. No brand filter — see
        # `_load_latest_n_posts` for the rationale.
        db_path = Path("data") / "x_monitoring.db"
        if not db_path.exists():
            print(
                f"smoketest: --source=latest-n needs the DB at {db_path} "
                "— run a cycle first or pass --source=fixture",
                file=sys.stderr,
            )
            return 2
        store = Store(db_path, auto_migrate=True)
        try:
            posts, posts_with_no_brand_skipped = _load_latest_n_posts(
                store, args.latest
            )
            brand_registry_rows = store.read_brands()
            args._role_lookup_store = store
            return _run_pipeline(
                posts, brand_registry_rows, args,
                posts_with_no_brand_skipped=posts_with_no_brand_skipped,
            )
        finally:
            store.close()

    db_path = Path("data") / "x_monitoring.db"
    if not db_path.exists():
        print(
            f"smoketest: db not found at {db_path} — "
            "run a cycle first or pass --source=fixture",
            file=sys.stderr,
        )
        return 2

    store = Store(db_path, auto_migrate=True)
    try:
        # The runner is offline-friendly: when no client is
        # configured the LLM call short-circuits. Tests inject
        # a fake by setting the env var ANTHROPIC_API_KEY (the
        # real client falls back to no-op), but for a real
        # smoketest against a fresh DB we use the real client.
        posts, posts_with_no_brand_skipped = _load_latest_cycle_posts(
            store, None, args.limit
        )
        brand_registry_rows = store.read_brands()
        args._role_lookup_store = store
        return _run_pipeline(
            posts, brand_registry_rows, args,
            posts_with_no_brand_skipped=posts_with_no_brand_skipped,
        )
    finally:
        store.close()


def _run_pipeline(
    posts: list[dict],
    brand_registry_rows: list,
    args,
    *,
    posts_with_no_brand_skipped: int = 0,
    translation_errors_override: dict | None = None,
) -> int:
    """Run the post-fetch pipeline against `posts` and print the
    smoketest report. Returns 0, or 1 if --strict-budget and total
    elapsed > 90s.

    U5: `posts_with_no_brand_skipped` is the count of posts excluded
    from the input because the keyword detector found no monitored
    brand attribution. Reported in the report header.

    U7: `translation_errors_override` lets tests inject a pre-built
    `translation_errors` dict (used by the U7 test for the "the LLM
    call raised" path). When None, the dict is built from the
    actual call below.
    """
    # Local imports — these are also imported inside main() but
    # we re-import here so the helper is callable from both
    # the fixture path and the DB path. Tests that monkeypatch
    # `x_monitor.translator.AnthropicClaudeClient` see the
    # patched value through the standard `from x_monitor.X import`
    # resolution.
    from x_monitor.translator import (
        AnthropicClaudeClient,
        translate_batch_pragmatics,
        _MAX_RETRIES,
    )
    from x_monitor.attribution import classify_pragmatics_full

    print(f"smoketest: source={args.source} n_posts={len(posts)}")
    if not posts:
        print("smoketest: no posts to process; nothing to report")
        return 0

    # Role annotation (--include-all-list-posts / api-query Call A):
    # load the DB-canonical role per author_handle so the renderer
    # can show `role=official|staff|community|none` next to each post.
    # Only populated when the smoketest was launched from the api-query
    # path (where we have a `store` reference); the latest-cycle /
    # latest-n / fixture paths don't bother since the per-post author
    # context there is already in-DB.
    role_by_handle: dict[str, str] = {}
    role_store = getattr(args, "_role_lookup_store", None)
    if role_store is not None:
        handles = sorted({
            p.get("author_handle") for p in posts
            if p.get("author_handle")
        })
        role_by_handle = _load_handle_roles(role_store, handles)

    client = AnthropicClaudeClient()

    # --- Stage 1: translate_batch_pragmatics (U3) --------------------
    translation_errors: dict[str, dict] = translation_errors_override or {}
    t0 = time.monotonic()

    def _record_batch_error(batch: list[dict], exc: Exception) -> None:
        """U7: attribute a per-batch translation failure to every
        tweet in the input batch. The translator calls this once per
        batch when the LLM call raised OR the response failed to parse.
        """
        for t in batch:
            tid = str(t.get("tweet_id") or t.get("id"))
            translation_errors[tid] = {
                "class": exc.__class__.__name__,
                "msg": str(exc)[:200],
                "retries": _MAX_RETRIES,
            }

    try:
        translation_rows = translate_batch_pragmatics(
            posts, ["en", "zh_cn"], client,
            on_batch_error=_record_batch_error if not translation_errors_override else None,
        )
    except Exception as exc:
        # Defensive: if translate_batch_pragmatics raises OUT (not
        # caught internally), still attribute the failure per-tweet.
        print(f"smoketest: translate stage raised: {exc}",
              file=sys.stderr)
        translation_rows = []
        if not translation_errors_override:
            _record_batch_error(posts, exc)
    t_translate_ms = int((time.monotonic() - t0) * 1000)

    # --- Stage 2: classify_pragmatics_full (U4) ----------------------
    t0 = time.monotonic()
    classification_rows: dict[str, list[dict]] = {}
    unsanctioned_flags_by_post: dict[str, list[str]] = {}
    for post in posts:
        brand_ids = post.get("brand_ids") or []
        if not brand_ids:
            continue
        try:
            cls = classify_pragmatics_full(
                text=post.get("text") or "",
                brand_ids=list(brand_ids),
                brand_registry=brand_registry_rows,
                anthropic_client=client,
            )
        except Exception as e:
            print(
                f"smoketest: classify failed for tweet_id="
                f"{post.get('tweet_id')}: {e}",
                file=sys.stderr,
            )
            continue
        # U2a: cls is now {"by_brand": {...}, "unsanctioned_flags": [...]}.
        by_brand = cls.get("by_brand", {}) if isinstance(cls, dict) else {}
        for brand_id, prongs in by_brand.items():
            classification_rows.setdefault(
                str(post.get("tweet_id") or post.get("id")), []
            ).append({"brand_id": brand_id, **prongs})
        flags = cls.get("unsanctioned_flags", []) if isinstance(cls, dict) else []
        if flags:
            unsanctioned_flags_by_post[
                str(post.get("tweet_id") or post.get("id"))
            ] = list(flags)
    t_classify_ms = int((time.monotonic() - t0) * 1000)

    # --- Aggregate counts -----------------------------------------
    # n_translated = rows where the translator produced output
    # for AT LEAST one target locale (not both — under the
    # deterministic noop, English posts have text_en NULL but
    # text_zh_cn populated, and vice versa).
    n_translated = sum(
        1 for r in translation_rows
        if not r.get("translation_failed")
        and (
            r.get("text_en") is not None
            or r.get("text_zh_cn") is not None
            or r.get("literal_zh") is not None
        )
    )
    n_failed_translate = sum(
        1 for r in translation_rows if r.get("translation_failed")
    )
    n_classified_posts = len(classification_rows)
    n_discourse = sum(
        1 for rows in classification_rows.values()
        for r in rows if r.get("discourse_role") != "uncategorized"
    )
    n_nationalism = sum(
        1 for rows in classification_rows.values()
        for r in rows
        if r.get("china_nationalism") != "none"
        and r.get("us_nationalism") != "none"
    )
    n_unsanctioned = len(unsanctioned_flags_by_post)

    total_ms = t_translate_ms + t_classify_ms

    # --- Render ----------------------------------------------------
    print("")
    print("=== POST-FETCH SMOKETEST REPORT ===")
    print(f"posts_seen:          {len(posts)}")
    if posts_with_no_brand_skipped:
        # U5: surface the count so reviewers know why posts_seen
        # may be lower than the DB row count.
        print(f"posts_no_brand_skipped: {posts_with_no_brand_skipped}")
    print(f"n_translated:        {n_translated}")
    print(f"n_failed_translate:  {n_failed_translate}")
    print(f"n_classified:        {n_classified_posts}")
    print(f"n_discourse:         {n_discourse}")
    print(f"n_nationalism:       {n_nationalism}")
    print(f"n_unsanctioned:      {n_unsanctioned}")
    print(f"t_translate_ms:      {t_translate_ms}")
    print(f"t_classify_ms:       {t_classify_ms}")
    print(f"t_total_ms:          {total_ms}")
    if total_ms > 90_000:
        print(
            f"WARNING: cycle exceeded 90s ceiling "
            f"(actual: {total_ms / 1000:.1f}s)",
            file=sys.stderr,
        )

    # Sample posts section (U7: include unsanctioned flags).
    sample = posts[: args.sample]
    print(_render_sample_posts(
        sample, translation_rows, classification_rows,
        unsanctioned_flags=unsanctioned_flags_by_post,
        role_by_handle=role_by_handle,
    ))

    # Unsanctioned flags summary.
    if unsanctioned_flags_by_post:
        print("")
        print(f"=== UNSANCTIONED FLAGS ({len(unsanctioned_flags_by_post)} posts) ===")
        for tid, flags in list(unsanctioned_flags_by_post.items())[:5]:
            print(f"  tweet_id={tid} flags={','.join(flags)}")

    # U7: per-tweet translation failure breakdown. Distinct from the
    # legacy `=== ERRORS ===` block (which only counted) — this one
    # tells the reviewer WHY the LLM call failed.
    if translation_errors:
        print("")
        print(
            f"=== TRANSLATION FAILURES ({len(translation_errors)} "
            "attributed) ==="
        )
        for tid, err in list(translation_errors.items())[:5]:
            msg_short = (err["msg"][:80] + "...") if len(err["msg"]) > 80 else err["msg"]
            print(
                f"  tweet_id={tid} class={err['class']} "
                f"retries={err['retries']} msg={msg_short!r}"
            )

    # Error summary.
    errors = [
        r for r in translation_rows if r.get("translation_failed")
    ]
    if errors:
        print("")
        print(f"=== ERRORS ({len(errors)} translation failures) ===")
        for r in errors[:5]:
            print(f"  tweet_id={r['tweet_id']} (translation_failed)")

    if args.strict_budget and total_ms > 90_000:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
