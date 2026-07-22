#!/usr/bin/env python3
"""Incremental bridge: import legacy x-monitor SQLite / run data into Django ORM (PostgreSQL).

Plan: U9 — bridge + validation harness for x-monitor v2 Django migration.

This script keeps PG in sync while legacy macOS launchd agents continue as
the harvest source. Two modes:

  --tail       (default) Query SQLite for rows since the last bridge run,
               then upsert them into PG via the Django ORM. Stores a sentinel
               timestamp file so re-runs import only new rows.

  --run-id ID  Read the legacy run summary JSON + raw tweet files for a
               specific run and import those tweets into PG.

Usage:
    python scripts/bridge_sqlite_to_pg.py --tail [--dry-run] [--source PATH]
    python scripts/bridge_sqlite_to_pg.py --run-id 20260722T043005_0000-e590e17b [--dry-run]
    python scripts/bridge_sqlite_to_pg.py --help
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import (  # noqa: F401
        Account,
        Post,
        PostBrand,
        PostBrandMention,
        PostBrandSignal,
    )

# ---------------------------------------------------------------------------
# Paths (computed before Django setup so --help works standalone)
# ---------------------------------------------------------------------------
SRC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_SOURCE = SRC / "data" / "x_monitoring.db"
DEFAULT_RUNS_DIR = SRC / "data" / "runs"
SENTINEL_FILE = SRC / "data" / ".bridge_last_tail_at"


# ---------------------------------------------------------------------------
# Lazy Django setup (deferred until after argparse, so --help works)
# ---------------------------------------------------------------------------

_django_ready: bool = False
_Account: Any = None
_Post: Any = None
_PostBrand: Any = None
_PostBrandMention: Any = None
_PostBrandSignal: Any = None


def _ensure_django() -> None:
    """Set up Django ORM (called after argparse, before data operations)."""
    global _django_ready, _Account, _Post, _PostBrand, _PostBrandMention, _PostBrandSignal
    if _django_ready:
        return
    try:
        import django
        django.setup()
    except Exception as exc:
        print(
            f"error: Django setup failed: {exc}\n"
            f"Make sure Django is installed and DATABASE_URL is configured.",
            file=sys.stderr,
        )
        sys.exit(1)
    from core.models import (  # noqa: F811
        Account,
        Post,
        PostBrand,
        PostBrandMention,
        PostBrandSignal,
    )
    _Account = Account
    _Post = Post
    _PostBrand = PostBrand
    _PostBrandMention = PostBrandMention
    _PostBrandSignal = PostBrandSignal
    _django_ready = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_dt(val: str | None) -> datetime | None:
    """Parse a datetime string into a timezone-aware UTC datetime."""
    if val is None:
        return None
    val = val.strip()
    if not val:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%a %b %d %H:%M:%S %z %Y",
    ):
        try:
            dt = datetime.strptime(val, fmt)
            return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _read_sentinel() -> datetime | None:
    """Read the last tail timestamp from the sentinel file."""
    if not SENTINEL_FILE.exists():
        return None
    try:
        content = SENTINEL_FILE.read_text().strip()
        return datetime.fromisoformat(content)
    except (ValueError, OSError):
        return None


def _write_sentinel(dt: datetime) -> None:
    """Write a tail timestamp to the sentinel file."""
    SENTINEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    SENTINEL_FILE.write_text(dt.isoformat())


def _parse_sqlite_json(val: str | None) -> Any:
    """Parse a SQLite TEXT blob as JSON, returning None for empty/None."""
    if val is None or not val.strip():
        return None
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


def _coerce_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# ORM persistence (mirrors monitor/cycle.py)
# ---------------------------------------------------------------------------


def _upsert_account_from_row(row: dict[str, Any], dry_run: bool) -> Any:
    """Upsert an Account from a SQLite row dict or raw tweet dict."""
    author_id = str(row.get("author_id") or row.get("authorId") or "")
    if not author_id:
        return None

    defaults: dict[str, Any] = {}
    handle = row.get("handle") or row.get("author_handle") or row.get("authorHandle") or ""
    if handle:
        defaults["handle"] = handle
    display_name = row.get("display_name") or row.get("author_name") or row.get("authorName") or ""
    if display_name:
        defaults["display_name"] = display_name
    bio = row.get("bio") or ""
    if bio:
        defaults["bio"] = bio
    verified = row.get("verified") or row.get("author_verified") or row.get("authorVerified")
    if verified is not None:
        defaults["verified"] = bool(int(verified) if isinstance(verified, (int, str)) and str(verified).isdigit() else verified)
    followers = row.get("followers_count") or row.get("author_followers_count") or row.get("authorFollowers")
    if followers is not None:
        defaults["followers_count"] = _coerce_int(followers)
    following = row.get("following_count") or row.get("author_following_count") or row.get("authorFollowing")
    if following is not None:
        defaults["following_count"] = _coerce_int(following)
    favourites = row.get("favourites_count") or row.get("author_favourites_count")
    if favourites is not None:
        defaults["favourites_count"] = _coerce_int(favourites)
    statuses = row.get("statuses_count") or row.get("author_statuses_count")
    if statuses is not None:
        defaults["statuses_count"] = _coerce_int(statuses)
    media = row.get("media_count") or row.get("author_media_count")
    if media is not None:
        defaults["media_count"] = _coerce_int(media)
    fast_followers = row.get("fast_followers_count") or row.get("author_fast_followers_count")
    if fast_followers is not None:
        defaults["fast_followers_count"] = _coerce_int(fast_followers)
    is_blue = row.get("is_blue_verified") or row.get("author_is_blue_verified")
    if is_blue is not None:
        defaults["is_blue_verified"] = bool(int(is_blue) if isinstance(is_blue, (int, str)) and str(is_blue).isdigit() else is_blue)
    verified_type = row.get("verified_type") or row.get("author_verified_type") or ""
    if verified_type:
        defaults["verified_type"] = verified_type
    profile_picture = row.get("profile_picture") or row.get("author_profile_picture") or ""
    if profile_picture:
        defaults["profile_picture"] = profile_picture
    location = row.get("location") or row.get("author_location") or ""
    if location:
        defaults["location"] = location
    description = row.get("description") or row.get("author_description") or ""
    if description:
        defaults["description"] = description
    profile_bio = row.get("profile_bio_text") or row.get("author_profile_bio_text") or ""
    if profile_bio:
        defaults["profile_bio_text"] = profile_bio

    followers_fetched_at = _parse_dt(row.get("followers_fetched_at"))
    if followers_fetched_at:
        defaults["followers_fetched_at"] = followers_fetched_at

    if dry_run:
        return None

    acc, _created = _Account.objects.update_or_create(
        author_id=author_id, defaults=defaults
    )
    return acc


def _upsert_post_from_row(
    row: dict[str, Any], account: Any, dry_run: bool
) -> Any:
    """Upsert a Post from a SQLite row dict or raw tweet dict."""
    tweet_id = str(row.get("tweet_id") or row.get("id") or "")
    if not tweet_id:
        return None

    defaults: dict[str, Any] = {}
    if account is not None:
        defaults["author"] = account

    handle = row.get("author_handle") or row.get("authorHandle") or row.get("handle") or ""
    if handle:
        defaults["author_handle"] = handle
    text = row.get("text") or ""
    if text:
        defaults["text"] = text
    lang = row.get("lang") or ""
    if lang:
        defaults["lang"] = lang

    created_at_str = row.get("created_at") or row.get("createdAt") or ""
    if created_at_str:
        dt = _parse_dt(created_at_str)
        if dt:
            defaults["created_at"] = dt

    like_count = _coerce_int(row.get("like_count") or row.get("likeCount"))
    if like_count is not None:
        defaults["like_count"] = like_count
    retweet_count = _coerce_int(row.get("retweet_count") or row.get("retweetCount"))
    if retweet_count is not None:
        defaults["retweet_count"] = retweet_count
    reply_count = _coerce_int(row.get("reply_count") or row.get("replyCount"))
    if reply_count is not None:
        defaults["reply_count"] = reply_count
    quote_count = _coerce_int(row.get("quote_count") or row.get("quoteCount"))
    if quote_count is not None:
        defaults["quote_count"] = quote_count

    in_reply = row.get("in_reply_to_user_id") or row.get("inReplyToUserId") or ""
    if in_reply:
        defaults["in_reply_to_user_id"] = str(in_reply)
    quoted = row.get("quoted_status_id") or row.get("quotedStatusId") or ""
    if quoted:
        defaults["quoted_status_id"] = str(quoted)
    conversation = row.get("conversation_id") or row.get("conversationId") or ""
    if conversation:
        defaults["conversation_id"] = str(conversation)

    entities = row.get("entities")
    if entities:
        if isinstance(entities, str):
            entities = _parse_sqlite_json(entities)
        if entities:
            defaults["entities"] = entities

    source_qid = row.get("source_query_id") or row.get("sourceQueryId") or ""
    if source_qid:
        defaults["source_query_id"] = source_qid

    created_at_epoch = _coerce_int(row.get("created_at_epoch") or row.get("createdAtEpoch"))
    if created_at_epoch is not None:
        defaults["created_at_epoch"] = created_at_epoch

    raw = row.get("raw")
    if raw:
        if isinstance(raw, str):
            raw = _parse_sqlite_json(raw)
        if raw:
            defaults["raw"] = raw
    elif not dry_run:
        # Store the row itself as raw for fidelity when coming from SQLite
        defaults["raw"] = dict(row)

    headline = row.get("headline") or ""
    if headline:
        defaults["headline"] = headline
    headline_source = row.get("headline_source") or ""
    if headline_source:
        defaults["headline_source"] = headline_source
    text_en = row.get("text_en") or ""
    if text_en:
        defaults["text_en"] = text_en
    text_zh_cn = row.get("text_zh_cn") or ""
    if text_zh_cn:
        defaults["text_zh_cn"] = text_zh_cn
    lang_detected = row.get("lang_detected") or ""
    if lang_detected:
        defaults["lang_detected"] = lang_detected
    quoted_text = row.get("quoted_text") or ""
    if quoted_text:
        defaults["quoted_text"] = quoted_text

    last_quote_count = _coerce_int(row.get("last_quote_count_seen"))
    if last_quote_count is not None:
        defaults["last_quote_count_seen"] = last_quote_count
    last_quote_fetched = _parse_dt(row.get("last_quote_fetched_at"))
    if last_quote_fetched:
        defaults["last_quote_fetched_at"] = last_quote_fetched

    if dry_run:
        return None

    post, _created = _Post.objects.update_or_create(
        tweet_id=tweet_id, defaults=defaults
    )
    return post


def _upsert_postbrands_from_row(
    row: dict[str, Any], post: Any, dry_run: bool
) -> int:
    """Upsert PostBrand + PostBrandMention + PostBrandSignal rows from a row dict.

    Returns the number of junction rows created.
    """
    tweet_id = str(row.get("tweet_id") or row.get("id") or "")
    if not tweet_id:
        return 0

    n = 0

    # PostBrand — from brand_ids if available
    brand_ids_data = row.get("brand_ids")
    if brand_ids_data:
        if isinstance(brand_ids_data, str):
            brand_ids_data = _parse_sqlite_json(brand_ids_data)
    if isinstance(brand_ids_data, list):
        for bid in brand_ids_data:
            if bid and isinstance(bid, str) and bid != "_unattributed":
                if not dry_run:
                    _PostBrand.objects.get_or_create(post=post, brand_id=bid)
                n += 1

    # PostBrandMention — from mentions if available
    mentions_data = row.get("mentions")
    if mentions_data:
        if isinstance(mentions_data, str):
            mentions_data = _parse_sqlite_json(mentions_data)
    if isinstance(mentions_data, list):
        seen_sources: set[tuple[str, str]] = set()
        for m in mentions_data:
            if not isinstance(m, dict):
                continue
            bid = m.get("brand_id", "")
            if not bid or bid == "_unattributed":
                continue
            source = m.get("source", "body_keyword")
            source_key = (bid, source)
            if source_key not in seen_sources:
                seen_sources.add(source_key)
                if not dry_run:
                    _PostBrandMention.objects.get_or_create(
                        post=post,
                        brand_id=bid,
                        source=source,
                        defaults={"raw_token": m.get("raw_token", "")},
                    )
                n += 1

    return n


# ---------------------------------------------------------------------------
# Tail mode: incremental sync from SQLite
# ---------------------------------------------------------------------------


def tail_from_sqlite(
    src_path: Path,
    dry_run: bool,
    since: datetime | None = None,
) -> dict[str, Any]:
    """Import rows from SQLite that were created since `since`.

    If `since` is None, reads the sentinel file. After a successful run,
    writes a new sentinel with the current time.

    Returns a counter dict: {accounts: N, posts: N, postbrands: N, errors: [...]}
    """
    if since is None:
        since = _read_sentinel()

    report: dict[str, Any] = {
        "mode": "tail",
        "accounts": 0,
        "posts": 0,
        "postbrands": 0,
        "errors": [],
        "since": since.isoformat() if since else None,
        "dry_run": dry_run,
    }

    if not src_path.exists():
        report["errors"].append(f"source DB not found: {src_path}")
        return report

    conn = sqlite3.connect(str(src_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    now_ts = datetime.now(UTC)
    since_iso = since.isoformat(timespec="seconds") if since else "1970-01-01T00:00:00"

    try:
        # ---- Accounts changed since last bridge ----
        # We use last_seen_at as the change indicator
        acct_cols = [
            "author_id", "handle", "display_name", "bio", "bio_fetched_at",
            "verified", "bio_contains_brand", "first_seen_at", "last_seen_at",
            "source_query_ids", "notes", "bio_en", "bio_zh_cn",
            "followers_count", "following_count", "favourites_count",
            "statuses_count", "media_count", "fast_followers_count",
            "is_blue_verified", "verified_type", "profile_picture",
            "location", "description", "profile_bio_text", "followers_fetched_at",
        ]
        acct_query = (
            f"SELECT {', '.join(acct_cols)} FROM accounts "
            f"WHERE last_seen_at >= ? ORDER BY author_id"
        )
        acct_rows = conn.execute(acct_query, [since_iso]).fetchall()
        for row in acct_rows:
            row_dict = dict(row)
            try:
                _upsert_account_from_row(row_dict, dry_run)
                report["accounts"] += 1
            except Exception as exc:
                report["errors"].append(f"account.{row_dict.get('author_id')}: {exc}")
        print(f"  accounts: {len(acct_rows)} changed", file=sys.stderr)

        # ---- Posts created since last bridge ----
        post_cols = [
            "tweet_id", "author_handle", "author_id", "text", "lang",
            "created_at", "fetched_at", "like_count", "retweet_count",
            "reply_count", "quote_count", "in_reply_to_user_id",
            "quoted_status_id", "conversation_id", "entities",
            "source_query_id", "raw", "headline", "headline_source",
            "text_en", "text_zh_cn", "lang_detected", "quoted_text",
            "last_quote_count_seen", "last_quote_fetched_at",
            "created_at_epoch",
        ]
        post_query = (
            f"SELECT {', '.join(post_cols)} FROM posts "
            f"WHERE fetched_at >= ? "
            f"ORDER BY created_at ASC"
        )
        post_rows = conn.execute(post_query, [since_iso]).fetchall()

        for row in post_rows:
            row_dict = dict(row)
            try:
                account = _upsert_account_from_row(row_dict, dry_run)
                post = _upsert_post_from_row(row_dict, account, dry_run)
                if dry_run or post is not None:
                    report["posts"] += 1
                if post is not None and not dry_run:
                    n_pb = _upsert_postbrands_from_row(row_dict, post, dry_run)
                    report["postbrands"] += n_pb
            except Exception as exc:
                report["errors"].append(f"post.{row_dict.get('tweet_id')}: {exc}")
        print(f"  posts: {len(post_rows)} since {since_iso}", file=sys.stderr)

    except Exception as exc:
        report["errors"].append(f"tail: {exc}")
    finally:
        conn.close()

    # Write sentinel
    if not dry_run and not report["errors"]:
        _write_sentinel(now_ts)
        print(f"  sentinel updated to {now_ts.isoformat()}", file=sys.stderr)
    elif dry_run:
        print("  ** DRY RUN — no writes, no sentinel update **", file=sys.stderr)

    return report


# ---------------------------------------------------------------------------
# Run-id mode: import raw JSON tweets from a specific legacy run
# ---------------------------------------------------------------------------


def import_run_by_id(
    run_id: str,
    runs_dir: Path,
    dry_run: bool,
) -> dict[str, Any]:
    """Import all raw tweets from a specific legacy run into PG.

    Finds the run summary JSON, then reads each raw tweet file listed in
    the run's queries[], upserts accounts and posts.
    """
    report: dict[str, Any] = {
        "mode": "run_id",
        "run_id": run_id,
        "accounts": 0,
        "posts": 0,
        "postbrands": 0,
        "files_processed": 0,
        "errors": [],
        "dry_run": dry_run,
    }

    # Find the run summary JSON
    summary_path = runs_dir / f"{run_id}.json"
    if not summary_path.exists():
        report["errors"].append(f"run summary not found: {summary_path}")
        return report

    try:
        summary = json.loads(summary_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        report["errors"].append(f"failed to read summary {summary_path}: {exc}")
        return report

    # Find all raw tweet files from the queries array
    raw_dir = runs_dir / "raw" / run_id
    if not raw_dir.exists():
        report["errors"].append(f"raw data directory not found: {raw_dir}")
        return report

    raw_paths: list[Path] = []
    queries = summary.get("queries") or summary.get("calls") or []
    for q in queries:
        raw_path_ref = q.get("raw_path", "")
        if raw_path_ref:
            # raw_path is relative like "runs/raw/RUN_ID/filename.json"
            # Extract just the filename
            filename = Path(raw_path_ref).name
            candidate = raw_dir / filename
            if candidate.exists():
                raw_paths.append(candidate)

    # If no paths found via summary, scan the raw directory
    if not raw_paths:
        raw_paths = sorted(raw_dir.glob("*.json"))

    print(f"  run {run_id}: {len(raw_paths)} raw files found", file=sys.stderr)

    for rp in raw_paths:
        report["files_processed"] += 1
        print(f"    processing {rp.name} ...", file=sys.stderr)
        try:
            data = json.loads(rp.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            report["errors"].append(f"file {rp.name}: {exc}")
            continue

        if not isinstance(data, list):
            # Might be a dict with a 'tweets' or 'results' key
            if isinstance(data, dict):
                data = data.get("tweets") or data.get("results") or data.get("data") or []
            else:
                continue

        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                account = _upsert_account_from_row(item, dry_run)
                if dry_run or account is not None:
                    report["accounts"] += 1
                post = _upsert_post_from_row(item, account, dry_run)
                if dry_run or post is not None:
                    report["posts"] += 1
                if post is not None and not dry_run:
                    n_pb = _upsert_postbrands_from_row(item, post, dry_run)
                    report["postbrands"] += n_pb
            except Exception as exc:
                tid = str(item.get("id") or item.get("tweet_id") or "?")
                report["errors"].append(f"tweet {tid} in {rp.name}: {exc}")

    return report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Incremental bridge: sync legacy SQLite / run data to Django ORM (PG).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/bridge_sqlite_to_pg.py --tail\n"
            "  python scripts/bridge_sqlite_to_pg.py --tail --dry-run\n"
            "  python scripts/bridge_sqlite_to_pg.py --run-id 20260722T043005_0000-e590e17b\n"
            "  python scripts/bridge_sqlite_to_pg.py --tail --source /custom/path.db"
        ),
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--tail",
        action="store_true",
        default=True,
        help="Incremental mode: import rows from SQLite since the last bridge run (default).",
    )
    mode_group.add_argument(
        "--run-id",
        type=str,
        default=None,
        metavar="RUN_ID",
        help="Import raw tweet data from a specific legacy run (by run ID).",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be imported; do not write to Django DB.",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=str(DEFAULT_SOURCE),
        metavar="PATH",
        help=f"Path to the legacy SQLite database (default: {DEFAULT_SOURCE}).",
    )
    parser.add_argument(
        "--runs-dir",
        type=str,
        default=str(DEFAULT_RUNS_DIR),
        metavar="PATH",
        help=f"Path to the legacy runs directory (default: {DEFAULT_RUNS_DIR}).",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        metavar="ISO_DATETIME",
        help="Override the tail 'since' timestamp (ISO 8601). Only for --tail mode.",
    )

    args = parser.parse_args()

    # Lazy Django setup — after argparse, before any ORM operations
    if not args.dry_run:
        _ensure_django()

    # Resolve paths
    source_path = Path(args.source)
    runs_dir = Path(args.runs_dir)

    print("=" * 64, file=sys.stderr)
    print("Bridge: Legacy -> Django ORM (PostgreSQL)", file=sys.stderr)
    print(f"  Dry run: {args.dry_run}", file=sys.stderr)
    print("=" * 64, file=sys.stderr)

    report: dict[str, Any]

    if args.run_id:
        # --run-id mode
        print(f"\nMode: --run-id {args.run_id}", file=sys.stderr)
        print(f"  Runs dir: {runs_dir}", file=sys.stderr)
        report = import_run_by_id(
            run_id=args.run_id,
            runs_dir=runs_dir,
            dry_run=args.dry_run,
        )
    else:
        # --tail mode (default)
        print(f"\nMode: --tail", file=sys.stderr)
        print(f"  Source DB: {source_path}", file=sys.stderr)

        since: datetime | None = None
        if args.since:
            since = _parse_dt(args.since)
            if since is None:
                print(f"error: could not parse --since value: {args.since}", file=sys.stderr)
                sys.exit(2)
            print(f"  Since (override): {since.isoformat()}", file=sys.stderr)
        else:
            saved = _read_sentinel()
            if saved:
                since = saved
                print(f"  Since (sentinel): {saved.isoformat()}", file=sys.stderr)
            else:
                print("  Since: (no sentinel — full import)", file=sys.stderr)

        report = tail_from_sqlite(
            src_path=source_path,
            dry_run=args.dry_run,
            since=since,
        )

    # ---- Summary ----
    print("\n" + "=" * 64, file=sys.stderr)
    for key in ("accounts", "posts", "postbrands"):
        print(f"  {key}: {report.get(key, 0)}", file=sys.stderr)
    if report.get("files_processed"):
        print(f"  files_processed: {report['files_processed']}", file=sys.stderr)
    if report.get("errors"):
        print(f"  errors: {len(report['errors'])}", file=sys.stderr)
        for err in report["errors"][:5]:
            print(f"    - {err}", file=sys.stderr)
        if len(report["errors"]) > 5:
            print(f"    ... and {len(report['errors']) - 5} more", file=sys.stderr)
    if args.dry_run:
        print("  ** DRY RUN — no writes performed **", file=sys.stderr)
    print("=" * 64, file=sys.stderr)

    # Emit JSON report to stdout
    print(json.dumps(report, indent=2, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
