# {{AGENT_ATTRIBUTION}}
"""U7: one-cycle post-fetch smoketest runner.

Plan: docs/plans/2026-07-02-002-feat-streamlined-post-fetch-pipeline-plan.md
(Unit 7 of 8). Exercises the entire post-fetch pipeline (U3
translate + U4 classify) against either the most recent cycle's
kept posts OR a fixture file, and prints:

  - counts per stage (n_classified, n_translated, n_discourse,
    n_nationalism)
  - per-stage timing in milliseconds
  - 5 sample posts with all 7 annotation fields aligned for
    eyeball coherence (text + text_en + literal_zh + discourse_role
    + cn_equivalent + china_nationalism + us_nationalism)
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


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="post_fetch_smoketest",
        description="Run the post-fetch pipeline once and print results",
    )
    p.add_argument(
        "--source",
        choices=["latest-cycle", "fixture"],
        default="latest-cycle",
        help="Where to source the kept posts from (default: latest-cycle).",
    )
    p.add_argument(
        "--fixture",
        type=Path,
        help="JSONL fixture file of {tweet_id, text, attributed_brands}. "
             "Required when --source=fixture.",
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
        help="Cap on posts processed (default: 200).",
    )
    return p.parse_args(argv)


def _load_latest_cycle_posts(
    store, anthropic_client, limit: int
) -> list[dict]:
    """Pull the most recent kept posts from the DB and use the
    deterministic brand-keyword detector to assign brand_ids.

    The classifier must NEVER rely on `posts_brands.brand_id`
    alone — that table was populated by the noisy body-keyword
    scan (e.g. Spanish "llama" matches as a verb get attributed
    to the llama brand). For the post-fetch classifier we want
    the same keyword machinery the LLM is told to trust, applied
    deterministically to the post text.
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
        SELECT p.tweet_id, p.text, p.lang_detected
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
            "brand_id": brand_ids[0] if brand_ids else "",
            "brand_ids": brand_ids,
        })
    return out


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
                "brand_id": (row.get("attributed_brands") or [""])[0],
                "brand_ids": row.get("attributed_brands") or [],
            })
    return out


def _render_sample_posts(
    sample_posts: list[dict],
    translation_rows: list[dict],
    classification_rows: dict[str, list[dict]],
    unsanctioned_flags: dict[str, list[str]] | None = None,
) -> str:
    """Render N posts with all 7 annotation fields aligned.

    U7: supports multi-value post_types[] and discourse_roles[] per
    brand row. Each (brand × post_type × discourse_role) tuple
    gets its own rendered line.

    `unsanctioned_flags` is an optional per-post_id list of flag values
    that get surfaced in a dedicated section at the end.
    """
    unsanctioned_flags = unsanctioned_flags or {}
    trans_by_id = {r["tweet_id"]: r for r in translation_rows}
    lines: list[str] = []
    lines.append("")
    lines.append("=== SAMPLE POSTS ===")
    for i, post in enumerate(sample_posts, 1):
        tid = str(post.get("tweet_id") or post.get("id"))
        lines.append("")
        lines.append(f"--- Post {i} (tweet_id={tid}) ---")
        lines.append(f"text:        {post.get('text', '')}")
        tr = trans_by_id.get(tid, {})
        lines.append(f"text_en:     {(tr.get('text_en') or '')}")
        lines.append(f"literal_zh:  {(tr.get('literal_zh') or tr.get('text_zh_cn') or '')}")
        # U7: discourse may now be an array; join for display.
        disc_val = tr.get("discourse_role", "uncategorized")
        if isinstance(disc_val, list):
            disc_val = ",".join(disc_val) if disc_val else "uncategorized"
        lines.append(f"discourse:   {disc_val}")
        lines.append(f"cn_equiv:    {(tr.get('cn_equivalent') or '')}")
        lines.append(f"annotation:  {(tr.get('annotation') or '(none)')}")
        # U7: per-post unsanctioned flags (if any).
        flags = unsanctioned_flags.get(tid, [])
        if flags:
            lines.append(f"unsanctioned: {','.join(flags)}")
        # U7: render N rows per brand — one per (post_type × discourse_role).
        # If post_types / discourse_roles are arrays, expand. Otherwise
        # fall back to the single scalar values (legacy).
        for cls in classification_rows.get(tid, []):
            post_types = cls.get("post_types") or (
                [cls["post_type"]] if cls.get("post_type") else [""]
            )
            discourse_roles = cls.get("discourse_roles") or (
                [cls["discourse_role"]] if cls.get("discourse_role") else [""]
            )
            for pt in post_types:
                for dr in discourse_roles:
                    lines.append(
                        f"  [brand={cls['brand_id']}] "
                        f"pt={pt} sent={cls['sentiment']} "
                        f"disc={dr} "
                        f"cn={cls['china_nationalism']} us={cls['us_nationalism']}"
                    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.source == "fixture" and not args.fixture:
        print(
            "--source=fixture requires --fixture PATH",
            file=sys.stderr,
        )
        return 2
    if args.fixture and not args.fixture.exists():
        print(f"--fixture not found: {args.fixture}", file=sys.stderr)
        return 2

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
    # --source=fixture bypasses the DB entirely (the post set
    # comes from the JSONL file); only --source=latest-cycle
    # requires a DB on disk.
    if args.source == "fixture":
        # Fixture path was validated by argparse (existence + path).
        # Run the pipeline in-memory; no DB on disk is touched.
        posts = _load_fixture_posts(args.fixture)
        brand_registry_rows = []
        return _run_pipeline(posts, brand_registry_rows, args)

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
        posts = _load_latest_cycle_posts(store, None, args.limit)
        brand_registry_rows = store.read_brands()
        return _run_pipeline(posts, brand_registry_rows, args)
    finally:
        store.close()


def _run_pipeline(
    posts: list[dict],
    brand_registry_rows: list,
    args,
) -> int:
    """Run the post-fetch pipeline against `posts` and print the
    smoketest report. Returns 0, or 1 if --strict-budget and total
    elapsed > 90s."""
    # Local imports — these are also imported inside main() but
    # we re-import here so the helper is callable from both
    # the fixture path and the DB path. Tests that monkeypatch
    # `x_monitor.translator.AnthropicClaudeClient` see the
    # patched value through the standard `from x_monitor.X import`
    # resolution.
    from x_monitor.translator import (
        AnthropicClaudeClient,
        translate_batch_pragmatics,
    )
    from x_monitor.attribution import classify_pragmatics_full

    print(f"smoketest: source={args.source} n_posts={len(posts)}")
    if not posts:
        print("smoketest: no posts to process; nothing to report")
        return 0

    client = AnthropicClaudeClient()

    # --- Stage 1: translate_batch_pragmatics (U3) --------------------
    t0 = time.monotonic()
    try:
        translation_rows = translate_batch_pragmatics(
            posts, ["en", "zh_cn"], client,
        )
    except Exception as e:
        print(f"smoketest: translate stage raised: {e}",
              file=sys.stderr)
        translation_rows = []
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
    ))

    # Unsanctioned flags summary.
    if unsanctioned_flags_by_post:
        print("")
        print(f"=== UNSANCTIONED FLAGS ({len(unsanctioned_flags_by_post)} posts) ===")
        for tid, flags in list(unsanctioned_flags_by_post.items())[:5]:
            print(f"  tweet_id={tid} flags={','.join(flags)}")

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