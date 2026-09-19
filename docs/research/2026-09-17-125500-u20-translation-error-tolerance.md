# Translation error tolerance for the multilingual feed

Research date: 2026-09-17. Advisory only: existing acceptance gates are unchanged.

## What the sources establish

There is no universal acceptable percentage of erroneous translations. MQM (Multidimensional Quality Metrics) uses error severity, intended purpose, and a project-specific tolerance, often measured in weighted penalty points per 1,000 words. Its worked example allows ten minor errors or two major errors per 1,000 words. This is an illustrative configuration, not an industry-wide allowance, and a score of 99 does not mean 99% of posts are correct. [MQM scoring models](https://www.themqm.org/mqm-pillars/the-mqm-scoring-models/).

MQM distinguishes limited-impact minor errors from major changes that undermine meaning or usability; critical errors make content unfit for purpose or risk serious harm. Its described pass/fail model requires no critical errors in the evaluated content as well as meeting the chosen score threshold. [MQM values and scores](https://www.themqm.org/guidance/values-and-scores/).

TAUS/CNGL's established 2010 post-editing guidelines allow awkward grammar and style for a fit-for-purpose translation, while still requiring a comprehensible, accurate message. These guidelines describe desired edited quality, not a guaranteed accuracy rate for unattended machine translation. [TAUS/CNGL guidelines](https://taus-website-media.s3.amazonaws.com/images/stories/guidelines/taus-cngl-machine-translation-postediting-guidelines.pdf).

## Proposed policy for this product — not adopted

For an informational social feed, prioritize faithful meaning over polished prose. A practical initial target would be at least 99% of displayed translated post-language outputs free of material meaning errors on a representative sample. The 1% tolerance is our proposed operating target, not a number prescribed by the sources. Report each language direction separately; each translated output is one observation. Source-language copies are not successful translation calls.

Treat awkward but understandable wording separately. Wrong actors, reversed sentiment or negation, materially wrong quantities, omitted essential information, and whole outputs in the wrong language count as material defects. An untranslated heading needs contextual severity assessment: an ornamental heading differs from one that establishes the scope of a claim. Known severe misleading outputs should be blocked or corrected rather than knowingly published to fit an aggregate allowance. Zero observed severe errors in a release sample cannot prove zero underlying risk.

Track request failures and withheld translations separately from displayed-content quality, including coverage and latency, so withholding bad outputs cannot conceal poor availability. Cheap deterministic checks for unchanged source, protected values, missing output, and structure are distinct from semantic evaluation; none guarantees correct meaning. This recommendation creates no new LLM pass or mandatory human review.

## What our fresh-five test can tell us

The deliberately difficult sample produced ten EN/ZH outputs from five Japanese posts. One Chinese output was the complete unchanged Japanese source. The four designated heading translations succeeded; no entity-role confusion was observed in the five usable outputs for the three role probes. These are reproduction findings, not a representative 10% production error estimate. The earlier failures and current gate remain open. See [fresh-five evidence](../analysis/2026-09-17-124500-u20-five-post-error-reproduction.md).
