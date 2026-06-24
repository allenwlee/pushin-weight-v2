#!/usr/bin/env python3
"""v3: seed detection tables on fuchitalee. accounts-first then brands_accounts."""
import sqlite3, sys, yaml
from datetime import datetime, timezone
from pathlib import Path

db_path = sys.argv[1]
filters_dir = Path('/Users/fuchitalee/development/minimax-marketing/worktrees/v18-unit4-call-path/x-monitoring/data/filters')
now = datetime.now(timezone.utc).isoformat()
conn = sqlite3.connect(db_path)
conn.execute('PRAGMA foreign_keys = ON')

print('[1/4] Backfilling accounts from posts.author_handle...')
rows = conn.execute("SELECT DISTINCT author_handle FROM posts WHERE author_handle IS NOT NULL AND author_handle != ''").fetchall()
n_accts = 0
for (handle,) in rows:
    aid = 'synthetic:' + handle.lower()
    cur = conn.execute(
        'INSERT OR IGNORE INTO accounts (author_id, handle, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?)',
        (aid, handle, now, now))
    n_accts += cur.rowcount
conn.commit()
print(f'  +{n_accts} new accounts')

brand_yaml = {
    'deepseek': 'deepseek.yaml', 'glm': 'glm.yaml', 'inclusionai': 'inclusionai.yaml',
    'minimax': 'minimax.yaml', 'moonshot_kimi': 'moonshot_kimi.yaml',
    'qwen': 'qwen.yaml', 'xiaomi_mimo': 'xiaomi_mimo.yaml',
}

print('[2/4] Inserting accounts for canonical_handles...')
n_canon_accts = 0
for bid, yn in brand_yaml.items():
    p = filters_dir / yn
    if not p.exists():
        continue
    try:
        data = yaml.safe_load(p.read_text()) or {}
    except Exception as e:
        print(f'  {bid}: yaml error {e}')
        continue
    for handle in (data.get('canonical_handles') or []):
        aid = 'synthetic:' + handle.lower()
        cur = conn.execute(
            'INSERT OR IGNORE INTO accounts (author_id, handle, display_name, first_seen_at, last_seen_at) VALUES (?, ?, NULL, ?, ?)',
            (aid, handle, now, now))
        n_canon_accts += cur.rowcount
conn.commit()
print(f'  +{n_canon_accts} canonical accounts')

print('[3/4] Linking brands_accounts (canonical -> official)...')
total_ba = 0
for bid, yn in brand_yaml.items():
    p = filters_dir / yn
    if not p.exists():
        continue
    try:
        data = yaml.safe_load(p.read_text()) or {}
    except Exception:
        continue
    for handle in (data.get('canonical_handles') or []):
        aid = 'synthetic:' + handle.lower()
        cur = conn.execute(
            'INSERT OR IGNORE INTO brands_accounts (brand_id, author_id, role, added_at) VALUES (?, ?, ?, ?)',
            (bid, aid, 'official', now))
        total_ba += cur.rowcount
conn.commit()
print(f'  +{total_ba} brands_accounts')

print('[4/4] Seeding brand_keywords (must_have_any + cjk_tokens)...')
total_kw = 0
for bid, yn in brand_yaml.items():
    p = filters_dir / yn
    if not p.exists():
        continue
    try:
        data = yaml.safe_load(p.read_text()) or {}
    except Exception:
        continue
    toks = []
    for key in ('must_have_any', 'cjk_tokens'):
        for t in data.get(key) or []:
            if t and isinstance(t, str):
                toks.append(t.strip())
    for t in toks:
        cur = conn.execute(
            'INSERT OR IGNORE INTO brand_keywords (brand_id, pattern, is_regex, added_at) VALUES (?, ?, 0, ?)',
            (bid, t, now))
        total_kw += cur.rowcount
conn.commit()
print(f'  +{total_kw} brand_keywords')

print('--- post-seed row counts ---')
for tbl in ['accounts', 'brands_accounts', 'brand_hashtags', 'brand_keywords', 'brand_search_terms', 'search_queries']:
    n = conn.execute(f'SELECT COUNT(*) FROM {tbl}').fetchone()[0]
    print(f'  {tbl}: {n}')
conn.close()