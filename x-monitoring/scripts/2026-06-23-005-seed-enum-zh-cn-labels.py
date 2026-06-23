#!/usr/bin/env python3
"""Override / re-seed the Chinese labels for the 6 signals, 5 roles, 3 tiers.

Unit 6 (i18n plan): migration 007 seeded operator-curated Chinese labels
for the three enum families (signal / role / engagement_tier). This
script is the operator's escape hatch — it UPSERTs the label rows so
the operator can re-curate any translation without re-running the
migration. It MUST be run BEFORE the four backfill scripts in
U6 because the dashboard's chart labels and role bars read from
these label tables directly.

The default labels below are the same ones seeded by migration 007;
override any value to re-curate it. The script accepts a single
optional CLI arg: the path to a YAML file with the same shape. If
unspecified, the defaults are written.

Usage:
    python3 scripts/2026-06-23-005-seed-enum-zh-cn-labels.py /path/to/x.db
    python3 scripts/2026-06-23-005-seed-enum-zh-cn-labels.py /path/to/x.db /path/to/labels.yaml
"""
import sqlite3
import sys
from pathlib import Path
from typing import Any

# Default operator-curated zh_cn labels. Mirror these by changing the
# values here; the migration 007 default seeds are below. Each
# (key, label) pair is what the dashboard renders when the locale is
# zh_cn.
DEFAULT_ZH_CN_LABELS: dict[str, dict[str, str]] = {
    "signal": {
        "release": "发布",
        "community_question": "社区提问",
        "criticism": "批评",
        "commenter_capture": "评论互动",
        "praise": "称赞",
        "other": "其他",
    },
    "role": {
        "official": "官方",
        "community": "社区",
        "researcher": "研究者",
        "press": "媒体",
        "vendor": "厂商",
    },
    "engagement_tier": {
        "low": "低",
        "medium": "中",
        "high": "高",
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
                    INSERT INTO {labels_table} (key, locale, label)
                    VALUES (?, 'zh_cn', ?)
                    ON CONFLICT(key, locale) DO UPDATE SET label = excluded.label
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
                f"SELECT key, label FROM {table} WHERE locale = 'zh_cn' "
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
