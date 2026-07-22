#!/usr/bin/env python3
"""Override / re-seed the Chinese labels for the enum families.

Unit 6 (i18n plan): migration 008 seeded operator-curated Chinese
labels for the two remaining enum families (signal / role). U9
(migration 022) replaced the `signal` family with two new families
(`post_type` / `sentiment`); the operator's escape hatch now covers
those new families plus `role`.

This script UPSERTs the label rows so the operator can re-curate any
translation without re-running the migration. It MUST be run BEFORE
the four backfill scripts in U6 because the dashboard's chart labels
and role bars read from these label tables directly.

(Note: the `engagement_tier` family was dropped in migration 012, the
`role` family was trimmed from 5 to 3 values {official, staff,
community} in migration 016, and the `signal` family was REPLACED by
`post_type` + `sentiment` in U9 / migration 022. This script reflects
the post-U9 schema.)

The default labels below are the same ones seeded by migration 019
(for post_type + sentiment) and migration 016 (for role); override
any value to re-curate it. The script accepts a single optional CLI
arg: the path to a YAML file with the same shape. If unspecified, the
defaults are written.

Usage:
    python3 scripts/2026-06-23-005-seed-enum-zh-cn-labels.py /path/to/x.db
    python3 scripts/2026-06-23-005-seed-enum-zh-cn-labels.py /path/to/x.db /path/to/labels.yaml
"""
import sqlite3
import sys
from pathlib import Path
from typing import Any

# Default operator-curated zh_cn labels. Mirror these by changing the
# values here; the migration 019/016 default seeds are below. Each
# (key, label) pair is what the dashboard renders when the locale is
# zh_cn.
#
# U9: the legacy `signal` family is gone; we now expose `post_type`
# and `sentiment` instead (each with their own label table seeded by
# migration 019).
DEFAULT_ZH_CN_LABELS: dict[str, dict[str, str]] = {
    "post_type": {
        "buzz_releases": "动态发布",
        "hands_on_usage": "上手实测",
        "performance_comparisons": "性能对比",
        "feedback_questions": "反馈与提问",
    },
    "sentiment": {
        "positive": "正面",
        "negative": "负面",
        "neutral": "中性",
        "mixed": "复杂",
    },
    "role": {
        "official": "官方",
        "staff": "员工",
        "community": "社区",
    },
}


def load_overrides(path: Path | None) -> dict[str, dict[str, str]]:
    """Load optional YAML overrides; fall back to DEFAULT_ZH_CN_LABELS."""
    if path is None:
        return DEFAULT_ZH_CN_LABELS
    try:
        import yaml
    except ImportError:
        print(
            "yaml is required to load overrides; "
            "pip install pyyaml or omit the YAML path",
            file=sys.stderr,
        )
        sys.exit(2)
    with path.open(encoding="utf-8") as f:
        data: Any = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        print(f"invalid overrides: expected dict, got {type(data)}", file=sys.stderr)
        sys.exit(2)
    # Merge: user overrides win on a per-key basis; missing families
    # fall back to defaults.
    merged: dict[str, dict[str, str]] = {}
    for family, defaults in DEFAULT_ZH_CN_LABELS.items():
        merged[family] = dict(defaults)
        user_family = data.get(family) or {}
        if not isinstance(user_family, dict):
            print(
                f"invalid overrides['{family}']: expected dict, "
                f"got {type(user_family)}",
                file=sys.stderr,
            )
            sys.exit(2)
        merged[family].update(user_family)
    return merged


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "usage: 2026-06-23-005-seed-enum-zh-cn-labels.py "
            "<db_path> [overrides_yaml]",
            file=sys.stderr,
        )
        return 2
    db_path = Path(sys.argv[1]).resolve()
    if not db_path.exists():
        print(f"db not found at {db_path}", file=sys.stderr)
        return 2
    overrides_path = (
        Path(sys.argv[2]).resolve() if len(sys.argv) >= 3 else None
    )
    if overrides_path is not None and not overrides_path.exists():
        print(f"overrides yaml not found at {overrides_path}", file=sys.stderr)
        return 2

    labels = load_overrides(overrides_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        n_updated = 0
        for family, key_labels in labels.items():
            labels_table = f"{family}_labels"
            for key, label in key_labels.items():
                # UPSERT: if a row already exists for (key, 'zh_cn'),
                # update its label; else insert it. We don't touch the
                # English row here — operators should only curate
                # zh_cn through this script.
                cur = conn.execute(
                    f"""
                    INSERT INTO {labels_table} (key, lang, label)
                    VALUES (?, 'zh_cn', ?)
                    ON CONFLICT(key, lang) DO UPDATE SET label = excluded.label
                    """,
                    (key, label),
                )
                n_updated += cur.rowcount
        conn.commit()
        print(f"updated {n_updated} zh_cn label rows in {db_path.name}")
        # Print final state for operator verification.
        for family in labels:
            table = f"{family}_labels"
            rows = conn.execute(
                f"SELECT key, label FROM {table} WHERE lang = 'zh_cn' "
                f"ORDER BY key"
            ).fetchall()
            print(f"  {table} (zh_cn):")
            for key, label in rows:
                print(f"    {key} = {label}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
