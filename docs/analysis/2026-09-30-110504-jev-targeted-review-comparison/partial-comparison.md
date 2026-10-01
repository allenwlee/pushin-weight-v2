# Recorded limitation before any Jev calls

The four frozen DeepSeek requests completed. The original parser accepted all
baseline rows and all brand-interpretation rows, but only six justified-content
rows. In addition, the justified-content response nested geopolitical
explanations inside `advertising_marketing` instead of supplying the required
`claim`/`evidence` object. These are experiment failures, not valid promotion
explanations. The shared conditional instruction mentioning both role schemas
is a possible contributor; no prompt revision or replacement call is being made.

The original runner stopped before any Jev call. Continue only the independent,
valid portions of the already authorized comparison:

- A: all eight baseline cases, with the original frozen review questions.
- B/C: geopolitical cases only, provided both role decisions pass the unchanged
  application parser and every required geopolitical basis field passes the
  frozen evidence validator. B shows those three valid basis fields, C hides
  them; all other inputs must be identical.
- B/C promotion: not run. Record all four planned cases as unavailable in each
  arm, not as successes or silent exclusions. Do not spend on the unpaired C
  promotion cases when B has no valid promotion explanation.

This is an explicitly partial comparison, not the originally planned complete
three-arm comparison. Dropping the malformed, irrelevant promotion-basis field
from geopolitical B requests is a transport/input-construction deviation from
the original all-fields basis state; no label, source, quote, or claim is repaired.
Retain all raw outputs, invalid-row/basis diagnostics, and original contracts.
Do not infer promotion-explanation performance from geopolitical results.

The eight-case acceptance set, expected labels, scoring thresholds, questions,
and model identities remain frozen. No added case, prompt tuning, model retry,
or additional experiment. At most 16 Jev calls are now planned (eight A, four B,
four C), plus the four already completed DeepSeek calls; the original bounded
429/529 retry rule and 32-call/US$1 ceiling still apply. This smaller continuation
was recorded before observing any Jev result. No production changes.
