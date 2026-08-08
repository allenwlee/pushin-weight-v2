# Iteration 003 (v22) — Feed engagement + avatar circles (P0 #3 + #4 of 5)

**Date:** 2026-08-08
**Branch:** feat/v20-homepage-phase-a (carrying v22 work)
**Scope:** fix P0 #3 (Feed engagement counts: 👥/♥/↻/💬) and P0 #4 (Feed avatar circles) from iter 1 audit.

## Step 1 — Regression Net

Pre-edit: 37/0 PASS

## Implementation

### `monitor/views.py` — added 3 helper functions

```python
def _avatar_initials(handle: str) -> str:
    """1-2 char uppercase initials from X handle."""

def _avatar_color(handle: str) -> str:
    """Stable per-handle HSL color (djb2 hash → hue 0..359, S 55%, L 45%)."""

def _engagement_pretty(followers, likes, rts, replies) -> dict:
    """Compact counters (24.6k / 1.2k / 340 / 89)."""
```

Extended `_post_to_wire` return dict with 5 new fields:
- `retweet_count`, `reply_count`, `quote_count` (from `Post`)
- `avatar_initials`, `avatar_color` (derived from author handle)
- `engagement_pretty` (compact counts for 👥/♥/↻/💬)

No schema changes — all data was already on `Post` and `Account`.

### `monitor/templates/monitor/_feed_initial.html` — render avatar + engagement

Wrapped handle cell in `<div class="feed-author">` containing the new `<span class="avatar">` circle plus the existing handle link. Added `<div class="feed-engagement">` block with 4 `.engagement-stat` spans (👥/♥/↻/💬) below the handle.

### `monitor/static/home-v20.css` — added `.feed-author`, `.avatar`, `.feed-engagement`, `.engagement-stat`, `.engagement-icon`

24px circle, white initials, flexbox layout. Color comes from inline `style="background: hsl(...)"`.

### `tests/regression_net.py` — added 9 new assertions

- `_check_feed_engagement(html)`: feed has ≥1 engagement block; every block has all 4 stat icons (👥/♥/↻/💬 HTML entities).
- `_check_feed_avatars(html)`: feed has ≥1 avatar circle; avatar color is valid hsl(...); initials are 1-2 chars [A-Z?]; multiple avatars have varied colors.

## Step 1 — Regression Net (post-edit)

```
Passed: 46
Failed: 0
```

(37 →46: 6 engagement + 3 avatar assertions all PASS.)

## Live HTML verification

```html
<span class="avatar" style="background: hsl(19, 55%, 45%)" aria-hidden="true">HI</span>
<span class="avatar" style="background: hsl(185, 55%, 45%)" aria-hidden="true">JA</span>
<span class="avatar" style="background: hsl(322, 55%, 45%)" aria-hidden="true">TI</span>
```

```html
<div class="feed-engagement">
  <span class="engagement-stat"><span class="engagement-icon" aria-hidden="true">&#128101;</span> 24.6k</span>
  <span class="engagement-stat"><span class="engagement-icon" aria-hidden="true">&#9825;</span> 1</span>
  <span class="engagement-stat"><span class="engagement-icon" aria-hidden="true">&#8634;</span> 0</span>
  <span class="engagement-stat"><span class="engagement-icon" aria-hidden="true">&#128172;</span> 0</span>
</div>
```

45 unique avatar colors across the feed (one per row). Format matches v22-master mockup exactly.

## P0 status after iter 3

| # | P0 gap | Status |
|---|---|---|
| 1 | Top Voices body | STILL OPEN (DB query needed) |
| 2 | Trending %change deltas | ✅ RESOLVED (iter 2) |
| 3 | Feed engagement counts | **RESOLVED** (this iter) |
| 4 | Feed avatar circles | **RESOLVED** (this iter) |
| 5 | Locale default = zh_cn | DROPPED (false positive in iter 1) |

**3 of 4 real P0 gaps now closed. 1 remains: Top Voices body.**

## Step 8 — Stop rule status

Per per-iteration contract step 8: no regressions (37 pre-existing assertions still pass). **However**, step 8 says don't declare PASS while P0 audit failures remain open. 1 P0 gap remains (Top Voices). Goal hook continues holding.

## Next iter recommendation

Iter 004: Top Voices body. This requires:
1. Add `_multi_top_voices(window_days, limit)` view function that joins `Account` × `Post` × `Brand`, groups by author handle, returns top N by `(mention_count DESC, follower_count DESC)`.
2. Pass `top_voices` to the home template context.
3. Render inside the existing `<div class="top-voices-region">` (heading already there) — `@handle (☆ N)` cards.
4. Update regression net with assertions: top-voices region contains N handle links + ☆ marks.

This is the historical blocker (5+ iterations of attempts across v18-v20). The schema supports it (`Account.followers_count`, `Post.author`, `PostBrand.brand`); no migration needed.

## Verdict

**PASS for P0 #3 + #4 (Feed engagement + avatar circles). 3 of 4 real P0s now resolved. Goal condition `v22` still unmet (1 gap: Top Voices).**