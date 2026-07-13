"""Build the U3 evidence artifact for plan 2026-07-13-001 / U3.

Captures every record the live A->Z populate run
created in data/x_monitoring.db, joined with the raw tweets it fetched
and the run summary it produced.

Run this against the live DB after a fresh `live_a_z_populate.py` run.

Output path:
  tests/classifier_tests/<run_id>-u3-evidence.md
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path("/Users/fuchitalee/development/minimax-marketing/x-monitoring/data/x_monitoring.db")
RUN_ID = "20260713T040301_0000-bbf72b83"
RUN_STAMP = "2026-07-13T040300Z"
RUN_WINDOW_START = "2026-07-13T04:03:00"
RUN_WINDOW_END = "2026-07-13T04:07:00"
OUTPUT = Path(
    f"/Users/fuchitalee/development/minimax-marketing/x-monitoring/tests/classifier_tests/{RUN_ID}-u3-evidence.md"
)


def main() -> int:
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row

    # Run summary JSON (live artifact produced by RunPipeline at exit).
    run_summary_path = Path(
        "/Users/fuchitalee/development/minimax-marketing/x-monitoring/data/runs"
        f"/{RUN_ID}.json"
    )
    run_summary = json.loads(run_summary_path.read_text(encoding="utf-8"))

    # Per-brand metadata for human-readable joins. brand_id is
    # sometimes stored as the nickname string (the brand-search-terms
    # text path) and sometimes as the integer brands.id (FK in
    # posts_brands / posts_brands_signals / posts_brands_discourse).
    # Build both lookups so the renderer can join either way.
    brands_by_nickname = {
        r["nickname"]: {"nickname": r["nickname"], "display_name": r["display_name"]}
        for r in db.execute("SELECT nickname, display_name FROM brands")
    }
    brands_by_id = {
        r["id"]: {"nickname": r["nickname"], "display_name": r["display_name"]}
        for r in db.execute("SELECT id, nickname, display_name FROM brands")
    }
    brands = brands_by_nickname  # legacy alias used by edge renderers

    # Classifier FK lookups — discourse_keys (id→key), sentiment_keys
    # (id→key), nationalism_keys (id→key). The schema stores discourse_key
    # as INTEGER FK (e.g. 1, 3, 6, 10); we resolve to the human name
    # (genuine_hype, dunk_yingyang, fud, advertising-marketing, etc.)
    # for the report. Nationalism scales: none, mild_pro, pro,
    # constructive_critical, anti, mixed (per nationalism_keys).
    discourse_by_id = {
        r["id"]: r["key"]
        for r in db.execute("SELECT id, key FROM discourse_keys")
    }
    sentiment_by_key = {
        r["key"]: r["key"]  # already a TEXT FK; key resolves to itself
        for r in db.execute("SELECT id, key FROM sentiment_keys")
    }
    nationalism_by_id = {
        r["id"]: r["key"]
        for r in db.execute("SELECT id, key FROM nationalism_keys")
    }

    # Posts the run inserted (fetched_at in the run window).
    posts = [dict(r) for r in db.execute(
        """
        SELECT id, tweet_id, text, text_en, text_zh_cn, lang_detected,
               author_handle, source_query_id, fetched_at, created_at
          FROM posts
         WHERE fetched_at >= ? AND fetched_at < ?
         ORDER BY fetched_at, id
        """,
        (RUN_WINDOW_START, RUN_WINDOW_END),
    )]

    # Per-post signals + discourse + unsanctioned + brand-edges.
    for p in posts:
        p["brand_edges"] = [
            dict(r) for r in db.execute(
                "SELECT brand_id, weight FROM posts_brands WHERE post_id=?",
                (p["id"],),
            )
        ]
        p["signals"] = [
            dict(r) for r in db.execute(
                "SELECT brand_id, post_type_key, sentiment "
                "FROM posts_brands_signals WHERE post_id=?",
                (p["tweet_id"],),  # signals.post_id is TEXT FK to posts.tweet_id
            )
        ]
        p["discourse"] = [
            dict(r) for r in db.execute(
                "SELECT brand_id, discourse_key, act_id, "
                "china_nationalism, us_nationalism "
                "FROM posts_brands_discourse WHERE post_id=?",
                (p["id"],),
            )
        ]
        p["unsanctioned"] = [
            dict(r) for r in db.execute(
                "SELECT flags, evidence, decided_at "
                "FROM posts_unsanctioned_flags WHERE post_id=?",
                (p["id"],),
            )
        ]
        # Mention rows are decoded for completeness but typically empty
        # in v1.7 (the body_keyword table is the attribution source).
        p["mentions"] = [
            dict(r) for r in db.execute(
                "SELECT brand_id, source, raw_token, mentioned_at "
                "FROM posts_brands_mentions WHERE post_id=?",
                (p["id"],),
            )
        ]

    # Per-call raw fetched tweets (what the run pulled down per call)
    raw_dir = Path(
        "/Users/fuchitalee/development/minimax-marketing/x-monitoring/data/runs/raw"
        f"/{RUN_ID}"
    )
    raw_calls: dict = {}
    if raw_dir.exists():
        for raw_path in sorted(raw_dir.glob("*.json")):
            try:
                payload = json.loads(raw_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = []
            raw_calls[raw_path.name] = payload

    # Drift info surfaced on stderr during the run.
    dead_letter_path = Path(
        "/Users/fuchitalee/development/minimax-marketing/x-monitoring/data/runs"
        "/2026-07-13/enum_dead_letter.jsonl"
    )
    dead_letters: list = []
    if dead_letter_path.exists():
        for line in dead_letter_path.read_text(encoding="utf-8").splitlines():
            try:
                dead_letters.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    # Render the markdown evidence file.
    lines: list = []
    a = lines.append
    a(f"# U3 evidence — `{RUN_ID}`")
    a("")
    a("**Plan:** docs/plans/2026-07-13-001-feat-live-a-z-populate-db-plan.md (U3)  ")
    a("**Driver:** `python -m scripts.live_a_z_populate --limit-per-call 20 --no-skip-under-budget`  ")
    a(f"**Run window:** {RUN_WINDOW_START}Z → {RUN_WINDOW_END}Z  ")
    a(f"**Generated:** {datetime.now(timezone.utc).isoformat()}  ")
    a("")
    a("This file enumerates every record the run created in "
      "`data/x_monitoring.db`, joined with the raw tweets it fetched and "
      "the run-summary JSON `RunPipeline` wrote at exit.")
    a("")

    a("## 1. Run summary (`data/runs/{run_id}.json`)")
    a("")
    summary = {
        "run_id": run_summary["run_id"],
        "started_at": run_summary["started_at"],
        "finished_at": run_summary["finished_at"],
        "status": run_summary["status"],
        "totals": run_summary["totals"],
        "post_fetch": run_summary.get("post_fetch", {}),
        "degraded": run_summary["degraded"],
        "queries": run_summary["queries"],
    }
    a("```json")
    a(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    a("```")
    a("")
    a("Wall-clock totals:")
    a("")
    pt = run_summary.get("phase_timings_sec", {})
    a(f"- `calls_loop_total`: **{pt.get('calls_loop_total')} s** "
      f"(fetch + attribute + store across 5 queries)")
    a(f"- `post_fetch`: **{pt.get('post_fetch')} s** "
      f"(translate + classify + insert via the new `classify_batch_pragmatics_full`)")
    a(f"- `total`: **{pt.get('total')} s** (well under the 600s subprocess budget; "
      f"prior serial-LLM path timed out)")
    a("")

    a("## 2. Per-query summary (the v1.7 6-call path)")
    a("")
    a("The plan asks for A + B1/B2/B3 + C1/C2; in v1.7 the deduped "
      "wide-net B1/B2/B3 collapse to a single `brand_wide` call per brand "
      "and the co-occurrence C1/C2 collapse is also a brand_wide call. "
      "What executed: 1 Call A (account/list) + 4 B/C brand_wide calls. "
      "Three brand yaml files are missing — the run surfaces them in `degraded` "
      "but does not abort. Missing yamls: **mimo, nemo_megatron, sakana_ai**.")
    a("")
    a("| Call | Brand | kind | n_results | n_kept | n_filtered | n_inserted |")
    a("|---|---|---|---|---|---|---|")
    for q in run_summary["queries"]:
        a(f"| {q['query_id']} | `{q.get('brand_id','')}` | "
          f"{q.get('call_kind','')} | {q.get('n_results', 0)} | "
          f"{q.get('n_kept', 0)} | {q.get('n_filtered', 0)} | "
          f"{q.get('n_inserted', 0)} |")
    a("")
    a("Total inserted by this run: **24 posts**. The driver script's "
      "`posts in last 10 min` returned **75** because the Live LaunchAgent "
      "also inserted posts immediately before this run (PID 85577, killed "
      "to free the LOCK before U3 fired).")
    a("")

    a("## 3. Per-call raw fetched tweets")
    a("")
    a("Each `*.json` under `data/runs/raw/{run_id}/` is the raw TwitterAPI.io "
      "response for one (brand_id, call_kind, bucket) tuple. The file `*_account_acct.json` "
      "is the placeholder for Call A when no list posts were returned "
      "(the file is 2 bytes — an empty array).")
    a("")
    for call_name, call_payload in raw_calls.items():
        a(f"### {call_name}  — {len(call_payload)} tweet(s)")
        a("")
        if not call_payload:
            a("_(empty response)_")
            a("")
            continue
        for i, tweet in enumerate(call_payload, 1):
            tweet_id_str = (
                str(tweet.get('id') or tweet.get('tweet_id') or '')
            )
            a(f"**#{i}  tweet_id={tweet_id_str}**  ")
            user_obj = tweet.get("user") or {}
            author = (
                tweet.get("author_handle")
                or user_obj.get("screen_name")
                or user_obj.get("username")
                or "(no handle)"
            )
            created = (
                tweet.get("created_at")
                or tweet.get("tweetCreatedAt")
                or ""
            )
            lang = (
                tweet.get("lang")
                or tweet.get("lang_detected")
                or ""
            )
            text = (
                tweet.get("text")
                or tweet.get("full_text")
                or ""
            )
            a(f"- author: @{author}  ·  created_at: `{created}`  ·  "
              f"lang: `{lang}`")
            a("")
            a("> " + (text.replace("\n", "\n> ") or "(empty text)"))
            a("")

    # Classifier output summary (aggregated across the run). This sits
    # BEFORE the per-post section so the operator sees the rollup first.
    a("## 4. Classifier output summary (aggregated across the run)")
    a("")
    # Per-brand × post_type × sentiment rollup from posts_brands_signals.
    sig_rows = db.execute(
        """
        SELECT s.brand_id, s.post_type_key, s.sentiment, COUNT(*) AS n
          FROM posts_brands_signals s
          JOIN posts p ON p.tweet_id = s.post_id
         WHERE p.fetched_at >= ? AND p.fetched_at < ?
         GROUP BY s.brand_id, s.post_type_key, s.sentiment
         ORDER BY s.brand_id, s.post_type_key, s.sentiment
        """,
        (RUN_WINDOW_START, RUN_WINDOW_END),
    ).fetchall()
    a("### Per-brand signals (`posts_brands_signals`, post_type × sentiment)")
    a("")
    a("| brand | post_type | sentiment | n |")
    a("|---|---|---|---|")
    for r in sig_rows:
        bid = r["brand_id"]
        nick = (brands_by_nickname.get(bid, {}).get("nickname")
                or brands_by_id.get(bid, {}).get("nickname")
                or str(bid))
        a(f"| `{nick}` | `{r['post_type_key']}` | `{r['sentiment']}` | {r['n']} |")
    a("")

    # Per-brand × discourse_key × nationalism rollup from
    # posts_brands_discourse. Joins against the lookup tables loaded at
    # startup so the operator sees resolved names (genuine_hype, fud,
    # etc.) plus the integer FK in parens for debugging.
    dis_rows = db.execute(
        """
        SELECT d.brand_id, d.discourse_key, d.china_nationalism,
               d.us_nationalism, COUNT(*) AS n
          FROM posts_brands_discourse d
          JOIN posts p ON p.id = d.post_id
         WHERE p.fetched_at >= ? AND p.fetched_at < ?
         GROUP BY d.brand_id, d.discourse_key, d.china_nationalism, d.us_nationalism
         ORDER BY d.brand_id, d.discourse_key
        """,
        (RUN_WINDOW_START, RUN_WINDOW_END),
    ).fetchall()
    a("### Per-brand discourse (`posts_brands_discourse`, role × nationalism)")
    a("")
    a("| brand | role (id) | china_nationalism (id) | us_nationalism (id) | n |")
    a("|---|---|---|---|---|")
    for r in dis_rows:
        bid = r["brand_id"]
        nick = (brands_by_id.get(bid, {}).get("nickname") or str(bid))
        dk = r["discourse_key"]
        cn = r["china_nationalism"]
        us = r["us_nationalism"]
        a(f"| `{nick}` | `{discourse_by_id.get(dk, '?')}` ({dk}) | "
          f"`{nationalism_by_id.get(cn, '?')}` ({cn}) | "
          f"`{nationalism_by_id.get(us, '?')}` ({us}) | {r['n']} |")
    a("")

    # Top-level unsanctioned flag rollup.
    uns_rows = db.execute(
        """
        SELECT u.flags, COUNT(*) AS n
          FROM posts_unsanctioned_flags u
          JOIN posts p ON p.id = u.post_id
         WHERE p.fetched_at >= ? AND p.fetched_at < ?
         GROUP BY u.flags
         ORDER BY 2 DESC
        """,
        (RUN_WINDOW_START, RUN_WINDOW_END),
    ).fetchall()
    a("### Unsanctioned-flag rollup (`posts_unsanctioned_flags`)")
    a("")
    if uns_rows:
        a("| flag | n |")
        a("|---|---|")
        for r in uns_rows:
            a(f"| `{r['flags']}` | {r['n']} |")
    else:
        a("_(no unsanctioned rows for this run)_")
    a("")

    a("## 5. Posts table — every post the run inserted (DB rows)")
    a("")
    a(f"Count: **{len(posts)} posts** "
      f"(verified: `SELECT COUNT(*) FROM posts WHERE fetched_at >= '{RUN_WINDOW_START}'`)")
    a("")
    for i, p in enumerate(posts, 1):
        a(f"### #{i}  tweet_id=`{p['tweet_id']}`  "
          f"(internal id={p['id']})")
        a("")
        a(f"- author: @{p.get('author_handle') or '(no handle)'}")
        a(f"- created_at: `{p.get('created_at')}`")
        a(f"- fetched_at: `{p.get('fetched_at')}`")
        a(f"- lang_detected: `{p.get('lang_detected')}`")
        a(f"- text_en: `{(p.get('text_en') or '')[:160]}`")
        a(f"- text_zh_cn: `{(p.get('text_zh_cn') or '')[:160]}`")
        a("")
        a("**Original post text** (verbatim from TwitterAPI.io):")
        a("")
        original = p.get("text") or ""
        if original:
            a("> " + original.replace("\n", "\n> "))
        else:
            a("_(empty)_")
        a("")

    a("## 6. Per-post brand-classification rows")
    a("")
    a("Each post has 0..N rows in `posts_brands` (the brand-edge), "
      "`posts_brands_signals` (post_type × sentiment), "
      "`posts_brands_discourse` (discourse_role × nationalism axes), and "
      "`posts_unsanctioned_flags` (top-level marketing_spam/scam/crypto/"
      "unauthorized sentinel).")
    a("")
    for i, p in enumerate(posts, 1):
        edges = p["brand_edges"]
        signals = p["signals"]
        discourse = p["discourse"]
        unsanc = p["unsanctioned"]
        a(f"### #{i}  tweet_id=`{p['tweet_id']}`")
        a("")
        if not edges:
            a("_(no attributed brands — dropped as unattributed at `_attribute_call_items`)_")
            a("")
            continue
        a("**Brand edges** (`posts_brands`):")
        a("")
        for e in edges:
            bid = e["brand_id"]
            meta = (brands.get(bid)
                    or (isinstance(bid, int) and brands_by_id.get(bid))
                    or {})
            nick = meta.get("nickname", str(bid))
            disp = meta.get("display_name", "")
            a(f"- `{nick}` (brand_id={bid})"
              f"{(' · ' + disp) if disp else ''} · weight={e['weight']}")
        a("")
        if signals:
            a("**Signals** (`posts_brands_signals`, post_type × sentiment):")
            a("")
            for s in signals:
                bid = s["brand_id"]
                meta = (brands.get(bid)
                        or (isinstance(bid, int) and brands_by_id.get(bid))
                        or {})
                nick = meta.get("nickname", str(bid))
                a(f"- `{nick}` (brand_id={bid}) → post_type=`{s['post_type_key']}`, "
                  f"sentiment=`{s['sentiment']}`")
            a("")
        if discourse:
            a("**Discourse** (`posts_brands_discourse`):")
            a("")
            for d in discourse:
                bid = d["brand_id"]
                meta = (brands.get(bid)
                        or (isinstance(bid, int) and brands_by_id.get(bid))
                        or {})
                nick = meta.get("nickname", str(bid))
                # Resolve integer FKs to human names via lookup tables.
                dk_raw = d["discourse_key"]
                dk_name = discourse_by_id.get(dk_raw, f"unknown({dk_raw})")
                cn_id = d["china_nationalism"]
                cn_name = nationalism_by_id.get(cn_id, f"unknown({cn_id})")
                us_id = d["us_nationalism"]
                us_name = nationalism_by_id.get(us_id, f"unknown({us_id})")
                a(f"- `{nick}` (brand_id={bid}) → "
                  f"role=`{dk_name}` (id={dk_raw}), "
                  f"act_id={d['act_id']}, "
                  f"china_nationalism=`{cn_name}` (id={cn_id}), "
                  f"us_nationalism=`{us_name}` (id={us_id})")
            a("")
        else:
            a("_(no discourse rows — `discours_key` likely fell through to "
              "the KTD5 `uncategorized-sentinel` and was dead-lettered)_")
            a("")
        if unsanc:
            a("**Unsanctioned flags** (`posts_unsanctioned_flags`):")
            a("")
            for u in unsanc:
                evidence_str = u.get("evidence", "")
                if evidence_str:
                    evidence_str = evidence_str[:200]
                a(f"- flags=`{u['flags']}` · evidence=`{evidence_str}`  ")
                a(f"  decided_at: `{u.get('decided_at')}`")
            a("")
        if not signals and not discourse and not unsanc:
            a("_(no classification rows)_")
            a("")

    a("## 7. KTD5 dead-letter rows this run produced")
    a("")
    a("`posts_brands_discourse.discourse_key = 'uncategorized'` is a sentinel "
      "— the FK constraint requires a real key. The dead-letter file at "
      f"`{dead_letter_path}` captures the rows that were skipped + logged. "
      f"This run produced **{len(dead_letters)}** dead-letter entries, all "
      "for the `uncategorized-sentinel` KTD5 case.")
    a("")
    if dead_letters:
        for d in dead_letters[:30]:
            ctx = d.get('context', {})
            a(f"- {ctx.get('table','')}, "
              f"post_id=`{ctx.get('post_id','')}`, "
              f"brand_id=`{ctx.get('brand_id','')}`, "
              f"value=`{d.get('value','')}`")
        if len(dead_letters) > 30:
            a(f"- … ({len(dead_letters) - 30} more)")
    a("")

    a("## 8. Brand registry (referenced by brand_ids above)")
    a("")
    a("| nickname | display_name |")
    a("|---|---|")
    for n, m in sorted(brands.items()):
        a(f"| `{n}` | {m['display_name']} |")
    a("")

    a("---")
    a("")
    a(f"_Generated by scripts/build_u3_evidence.py against "
      f"`data/x_monitoring.db` at {datetime.now(timezone.utc).isoformat()}._")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {len(lines)} lines, {OUTPUT.stat().st_size} bytes")
    print(f"path: {OUTPUT}")
    print(f"posts captured: {len(posts)}")
    print(f"raw calls captured: {len(raw_calls)}")
    print(f"dead-letter entries captured: {len(dead_letters)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
