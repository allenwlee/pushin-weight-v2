# Why-first headline evaluation

- Run: `2026-08-15-owner-approved-why-first-evidence-contract-rerun-v4`
- Model: `deepseek-v4-pro`
- Calls used: 28
- Stop reason: `completed`
- Accounted input tokens: 212208
- Accounted cost: $0.105015

The JSON sibling is the reproducible machine record with all 28 bilingual
outputs editorially reviewed.

Every generated English and Simplified Chinese headline is reproduced in the
[readable headline appendix](2026-08-14-213446-why-first-headline-samples.md),
grouped by editorially accepted and rejected output.

## Decision

**Reject activation. No evidence-count policy or materiality policy is
frozen.** The run completed within its approved boundary, but it contains
critical failures at every tested evidence count. More excerpts did not
produce an editorial quality plateau.

Only three outputs were publishable: the pairwise high-content,
high-independence cases at 12 excerpts (`pair-10` and `pair-14`), plus the
750-character quiet-window density sentinel. The two content cases correctly
led with recurring reports of more downloads and improved intelligence. The
quiet case candidly said that the generic posts supplied no recurring reason.

Nine additional outputs passed deterministic validation but failed editorial
review. The most important repeated failure was turning many excerpts from one
source into plural “users reported” language. Other schema-valid failures
selected an unnecessary second candidate, described unsupported hands-on mix,
or substituted generic discussion and measurements for a content-derived why.

Sixteen outputs failed deterministic validation:

- five weak recurring explanations;
- four missing English subjects;
- two event anchors without supported events;
- two unused or unaligned quantitative facts;
- two malformed schemas;
- one missing evidence family.

## Evidence-count comparison

| Excerpts | Calls | Schema-valid | Editorially accepted | Average packet | Average input | Average latency |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | 6 | 1 | 0 | 19,838 bytes | 4,274 tokens | 6,736 ms |
| 12 | 6 | 4 | 2 | 31,247 bytes | 6,788 tokens | 5,962 ms |
| 24 | 10 | 3 | 1 | 43,016 bytes | 7,636 tokens | 6,193 ms |
| 48 | 6 | 4 | 0 | 82,542 bytes | 11,580 tokens | 6,048 ms |

Twelve excerpts performed best but still had critical failures in four of six
calls. Forty-eight excerpts more than doubled the average packet and increased
average provider input by about 71% versus 12, without improving deterministic
validity or producing any editorially accepted output. All four candidate caps
are therefore rejected; 48 is specifically rejected as higher-cost without a
quality gain.

## Resource accounting

- 28 of 28 authorized calls completed sequentially.
- Provider-reported input usage totaled 212,208 tokens.
- Accounted cost was $0.105015, below the $0.70 stop boundary.
- Total provider latency was 174,406 ms; no production writes, harvesting, or
  scheduled-worker actions occurred.
- The largest packet was 88,000 bytes, within the declared limit.

## Gate result

The live editorial gate fails because unsupported why claims, wrong subject
selection, and quiet-window overreach remain. The separate historical
calibration is also under-sampled for engagement and has no 365-day samples.
Per U6, configuration stays inactive and release work must not begin. Further
prompt-only paid reruns are not justified by this sequence; a future revision
would need a materially stronger deterministic semantic boundary or a
different generation architecture, followed by a newly authorized finite
evaluation.
