"""Cleanup script: undo the bogus canonical inserts from the pre-pass.

Background: Phase 2 v4 aiohttp pre-pass inserted 596 integer
author_ids via `INSERT ... ON CONFLICT (author_id) DO NOTHING`
between 2026-07-30 11:15 and the user's manual kill. Of those:
- 587 shared handle with an existing account (KTD10 disagreement)
- 9 were unique (legitimate canonicals)

The 587 bad rows point at handles that already exist in `accounts`,
creating new duplicate groups. The apply loop was supposed to
detect this via KTD10 and dead-letter, but the pre-pass INSERT
bypassed that check.

To restore the pre-apply state:
1. Find the 596 recent integer rows.
2. Split into KEEP (9 unique handles) and DELETE (587 dup handles).
3. For rows to DELETE: repoint any FK references (posts, APAs,
   brands) to the existing canonical handle, then DELETE.
4. For rows to KEEP: leave them alone (they're valid new canonicals).

This is the safest rollback path. It does NOT lose data.
"""
from django.db import connection

cur = connection.cursor()
# Identify the 596 recent integer rows
cur.execute("""
  SELECT author_id, handle, LOWER(handle) AS lhandle
  FROM accounts
  WHERE author_id ~ '^[0-9]+$' AND first_seen_at > '2026-07-30T11:15:00Z'
  ORDER BY author_id
""")
recent = cur.fetchall()
print(f"recent integer rows: {len(recent)}")

# Find which handles are in dup groups
cur.execute("""
  SELECT LOWER(handle) FROM accounts GROUP BY LOWER(handle) HAVING COUNT(*) > 1
""")
dup_handles = {row[0] for row in cur.fetchall()}
print(f"dup lhandles: {len(dup_handles)}")

bad_ids = [r[0] for r in recent if r[2] in dup_handles]
good_ids = [r[0] for r in recent if r[2] not in dup_handles]
print(f"bad (KTD10, in dup groups): {len(bad_ids)}")
print(f"good (unique handle): {len(good_ids)}")

# For each bad_id, find the existing canonical integer (the one
# that already has this handle) and move FK refs.
repointed = 0
for bad_id in bad_ids:
    cur.execute("SELECT LOWER(handle) FROM accounts WHERE author_id = %s", (bad_id,))
    row = cur.fetchone()
    if not row:
        continue
    lhandle = row[0]
    # existing canonical
    cur.execute("""
      SELECT author_id FROM accounts
      WHERE LOWER(handle) = %s AND author_id <> %s
      ORDER BY first_seen_at LIMIT 1
    """, (lhandle, bad_id))
    other = cur.fetchone()
    if not other:
        print(f"  WARN: bad_id {bad_id} handle={lhandle} has no other canonical; skipping")
        continue
    canonical = other[0]
    # posts
    cur.execute(
        "UPDATE posts SET author_id = %s WHERE author_id = %s AND LOWER(author_handle) = %s",
        (canonical, bad_id, lhandle),
    )
    posts_n = cur.rowcount
    # APAs
    cur.execute("UPDATE account_post_appearances SET author_id = %s WHERE author_id = %s", (canonical, bad_id))
    apa_n = cur.rowcount
    # brands
    cur.execute("UPDATE brands_accounts SET accounts_id = %s WHERE accounts_id = %s", (canonical, bad_id))
    brands_n = cur.rowcount
    # DELETE the bad row
    cur.execute("DELETE FROM accounts WHERE author_id = %s", (bad_id,))
    delete_n = cur.rowcount
    repointed += 1
    if repointed % 50 == 0:
        print(f"  repointed {repointed}/{len(bad_ids)}: {bad_id} -> {canonical} (posts={posts_n}, apa={apa_n}, brands={brands_n}, deleted={delete_n})")

print(f"\ntotal repointed: {repointed}")
print(f"good_ids kept (NOT touched): {len(good_ids)}")

# Verify
cur.execute("SELECT COUNT(*) FROM (SELECT handle FROM accounts WHERE handle IS NOT NULL GROUP BY handle HAVING COUNT(*) > 1) t")
print(f"dup_groups after cleanup: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM accounts")
print(f"total_accounts after cleanup: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM accounts WHERE author_id ~ '^[0-9]+$'")
print(f"integer_rows after cleanup: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM accounts WHERE author_id LIKE 'handle:%' OR author_id LIKE 'synthetic:%'")
print(f"placeholder_rows after cleanup: {cur.fetchone()[0]}")
