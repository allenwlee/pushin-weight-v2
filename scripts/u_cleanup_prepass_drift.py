"""Cleanup v3: undo v6's +1 dup group drift.

v6 had a +1 dup group drift. Find the recent integer rows that
are in dup groups and DELETE them.
"""
from django.db import connection

cur = connection.cursor()
cur.execute("""
  SELECT author_id, handle, LOWER(handle) AS lhandle
  FROM accounts
  WHERE author_id ~ '^[0-9]+$' AND first_seen_at > '2026-07-30T11:15:00Z'
  ORDER BY author_id
""")
recent = cur.fetchall()

cur.execute("""
  SELECT LOWER(handle) FROM accounts GROUP BY LOWER(handle) HAVING COUNT(*) > 1
""")
dup_handles = {row[0] for row in cur.fetchall()}

bad_ids = [r[0] for r in recent if r[2] in dup_handles]
good_ids = [r[0] for r in recent if r[2] not in dup_handles]
print(f"bad: {len(bad_ids)}, good: {len(good_ids)}")

for bad_id in bad_ids:
    cur.execute("SELECT LOWER(handle) FROM accounts WHERE author_id = %s", (bad_id,))
    lhandle = cur.fetchone()[0]
    cur.execute("""
      SELECT author_id FROM accounts
      WHERE LOWER(handle) = %s AND author_id <> %s
      ORDER BY first_seen_at LIMIT 1
    """, (lhandle, bad_id))
    other = cur.fetchone()
    if not other:
        continue
    canonical = other[0]
    cur.execute(
        "UPDATE posts SET author_id = %s WHERE author_id = %s AND LOWER(author_handle) = %s",
        (canonical, bad_id, lhandle),
    )
    cur.execute("UPDATE account_post_appearances SET author_id = %s WHERE author_id = %s", (canonical, bad_id))
    cur.execute("UPDATE brands_accounts SET accounts_id = %s WHERE accounts_id = %s", (canonical, bad_id))
    cur.execute("DELETE FROM accounts WHERE author_id = %s", (bad_id,))
    print(f"  {bad_id} -> {canonical}")

print(f"bad_ids cleaned: {len(bad_ids)}")

cur.execute("SELECT COUNT(*) FROM (SELECT handle FROM accounts WHERE handle IS NOT NULL GROUP BY handle HAVING COUNT(*) > 1) t")
print(f"dup_groups after cleanup: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM accounts")
print(f"total_accounts after cleanup: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM accounts WHERE author_id ~ '^[0-9]+$'")
print(f"integer_rows after cleanup: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM accounts WHERE author_id LIKE 'handle:%' OR author_id LIKE 'synthetic:%'")
print(f"placeholder_rows after cleanup: {cur.fetchone()[0]}")
