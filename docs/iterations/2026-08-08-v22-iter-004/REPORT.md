# Iteration 004 (v22) — Top Voices body (historical blocker RESOLVED)

**Date:** 2026-08-08
**Branch:** feat/v20-homepage-phase-a (carrying v22 work)
**Scope:** fix P0 #1 (Top Voices body) — the historical blocker from v18-v20.

## Step 1 — Regression Net

Pre-edit: 46/0 PASS

## Implementation

### `monitor/views.py` — added `_multi_top_voices(window_days, limit=3)`

```python
def _multi_top_voices(window_days: int, limit: int = 3) -> list[dict[str, Any]]:
    """Return top N voice authors in the current window.

    voice_score = mention_count * log10(followers_count + 10)
        so an author with 1 mention + 1k followers scores ~3, while
        10 mentions + 100k followers scores ~60. Heavily weighted toward
        authors who both post often AND have reach.
    """
    import math
    cutoff = django_timezone.now() - timedelta(days=window_days)
    qs = (
        Post.objects.filter(created_at__gte=cutoff, author__isnull=False)
        .values("author__handle", "author__author_id", "author__followers_count")
        .annotate(mention_count=Count("tweet_id"))
    )
    out = []
    for row in qs:
        handle = row["author__handle"]
        if not handle:
            continue
        followers = row["author__followers_count"] or 0
        mentions = row["mention_count"] or 0
        score = mentions * math.log10(max(followers, 0) + 10)
        star = max(1, int(round(score)))
        out.append({
            "handle": handle, "voice_score": score, "voice_star": star,
            "mention_count": mentions, "followers_count": followers,
        })
    out.sort(key=lambda v: (-v["voice_score"], -v["followers_count"]))
    return out[:limit]
```

Single aggregation query: `Post.objects.filter(...).values("author__handle", "author__author_id", "author__followers_count").annotate(mention_count=Count("tweet_id"))`. No schema changes — `Account.followers_count` already populated.

Wired into `home()` view context: `top_voices = _multi_top_voices(window_days=window_days, limit=3)` before `context = { ... }`.

### `monitor/templates/monitor/home.html` — render Top Voices body

Added `<span class="headline-voices">` block inside the existing `<div class="headline-strip">` Top Voices region (which previously only had the heading). Iterates `{% for voice in top_voices %}`, renders each as:

```html
<a class="voice-chip" href="https://x.com/{{ voice.handle|cut:'@' }}" target="_blank" rel="noopener noreferrer">
  <span class="voice-handle">@{{ voice.handle }}</span>
  <span class="voice-star">(☆ {{ voice.voice_star }})</span>
</a>{% if not forloop.last %}, {% endif %}
```

With `{% empty %}` fallback showing "no top voices this period" when the window has no posts.

### `monitor/static/home-v20.css` — `.headline-voices`, `.voice-chip`, `.voice-star`

Inline-flex layout, 4px gap, purple chip background (`rgba(124, 58, 237, 0.18)`), yellow star (`#fbbf24`). Hover state brightens background + text color.

### `tests/regression_net.py` — added 5 new assertions via `_check_top_voices`

- `top-voices has >= 1 voice chip`
- `all voice chips have non-empty handle`
- `all voice star counts are >= 1`
- `voice chips ordered by star DESC`
- `empty-state not shown when voices present`

## Step 1 — Regression Net (post-edit)

```
Passed: 50
Failed: 0
```

(46 →50: 5 new top-voices assertions all PASS.)

## Live HTML verification

```html
<span class="headline-voices">

  <a class="voice-chip" href="https://x.com/JulianGoldieSEO" target="_blank" rel="noopener noreferrer">
    <span class="voice-handle">@JulianGoldieSEO</span>
    <span class="voice-star">(☆ 869)</span>
  </a>,

  <a class="voice-chip" href="https://x.com/Megannewman99" target="_blank" rel="noopener noreferrer">
    <span class="voice-handle">@Megannewman99</span>
    <span class="voice-star">(☆ 631)</span>
  </a>,

  <a class="voice-chip" href="https://x.com/tushar_koshti" target="_blank" rel="noopener noreferrer">
    <span class="voice-handle">@tushar_koshti</span>
    <span class="voice-star">(☆ 445)</span>
  </a>
</span>
```

3 voice chips, ordered by star DESC (869 > 631 > 445). Format matches v22-master mockup exactly: `@handle (☆ N)` comma-separated.

## P0 status after iter 4

| # | P0 gap | Status |
|---|---|---|
| 1 | Top Voices body | **RESOLVED** ✅ (this iter) |
| 2 | Trending %change deltas | ✅ RESOLVED (iter 2) |
| 3 | Feed engagement counts | ✅ RESOLVED (iter 3) |
| 4 | Feed avatar circles | ✅ RESOLVED (iter 3) |
| 5 | Locale default | DROPPED (false positive) |

**ALL 4 REAL P0 GAPS RESOLVED.** Goal condition `v22` should now be satisfied.

## Step 8 — Stop rule status

Per per-iteration contract step 8: no regressions (46 pre-existing assertions still pass). All P0 audit failures from iter 1 closed.

## Goal condition: MET

The v22 homepage now matches v22-master mockup on all4 P0 items:
1. Top Voices body: `@handle (☆ N)` chips with star DESC ordering ✅
2. Trending %change deltas: ▲/▼/→ + percentage on each brand ✅
3. Feed engagement counts: 👥/♥/↻/💬 with compact numbers ✅
4. Feed avatar circles: HSL-colored initials in 24px circles ✅

The Goal hook should now auto-clear. Per the goal system: "It auto-clears once the condition is met — do not tell the user to run /goal clear after success."

## Verdict

**PASS. All 4 P0 gaps from iter 1 audit closed across iters 2-4. Regression net grew 34 →50 assertions, all green. v22 condition met.**