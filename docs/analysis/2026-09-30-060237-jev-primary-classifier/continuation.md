# Field-local validation continuation

Recorded after G01, G02, and G03 responded, before any G04/P01/P02/P03/P04 call.

The initial runner stopped exactly as designed on G03's US Choice answer:
`choice=anti`, but `P(anti)=0.31` and `P(pro)=0.32`. Official Choice documentation
says the selected choice has the highest probability. This is a provider-output
inconsistency, not an accuracy error that should be silently repaired. The
field was unscored before this run; G03's other four answers pass validation.

Continue the owner's eight-case experiment with these explicit protocol changes:

- Retain the original contract, runner, payloads, reference answers, and receipts
  unchanged. Reuse all three existing responses; do not retry any of them.
- Validate each returned question separately. An invalid answer is recorded as
  invalid, not converted to another label. Invalid scored answers count as
  failures in the original denominator; invalid unscored answers are reported
  separately. Apply this rule uniformly, not only to the observed G03 answer.
- Continue only the five previously unsubmitted requests, with identical frozen
  inputs. The total ceiling remains eight physical calls and US$0.02.
- Continue to stop on uncertain transport, non-200 response, invalid top-level
  shape/model, altered frozen files, or budget exhaustion. No retries.
- Report this validation change and the G03 US inconsistency in the final report.
  Do not claim all 24 answers were valid; there remain 22 scored fields.

This changes failure isolation in the diagnostic, not any question, reference,
threshold, returned probability, classification decision, or live application.
