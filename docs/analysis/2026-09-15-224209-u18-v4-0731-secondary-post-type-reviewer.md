# U18 V4 Flash 0731: secondary post-type reviewer

The first content and brand calls match the two-call 0731 architecture. A third sequential call sees the primary post types and may add omitted concrete types only. It cannot remove a label or change another axis.

## Results

| Configuration | Overall agreement | Post-type exact sets | Post-type recall | Post-type precision |
|---|---:|---:|---:|---:|
| 0731 primary + add-only reviewer | 70.0% (231/330) | 8/46 | 56.8% | 58.1% |
| Same-run 0731 primary | 70.3% (232/330) | 9/46 | 54.7% | 59.1% |
| Prior 0731 two-call | 70.6% (233/330) | 9/46 | 53.7% | 57.3% |
| 0731 split-three-call | 69.4% (229/330) | 12/46 | 54.7% | 72.2% |
| V4.1 two-call | 65.2% (215/330) | 9/46 | 59.0% | 64.4% |

## Reviewer behavior

- Decisions receiving additions: 5.
- Added labels matching reviewed owner controls: 2.
- Added labels outside reviewed owner controls: 3.
- Added labels where the owner left the field unreviewed: 0.
- Total measured cost for 40 posts: $0.003832 with fee.
- Estimated primary-parallel-plus-review time: 37.2s.
- No retries, LLM repairs, fallbacks, database writes, or production changes occurred.
