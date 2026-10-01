# Jev multilingual, full-taxonomy diagnostic

## Plain-English Summary

Test Jev as the classifier for Japanese, Simplified Chinese, Korean, and the
next three most frequent languages in the production database. Classification
means choosing the existing categories, not generating entity names or evidence
quotations. Assume a separate extractor handles those open-ended outputs.

This is a bounded experiment, not a model switch or deployment. Existing
classifications are not ground truth. Reference judgments and the exact Jev
questions will be frozen before inference. Report category and language results,
positive-label precision/recall, whole-post correctness, uncertainty, and
structural consistency separately; abundant negative labels must not mask errors.

## Authority and bounds fixed before data collection

Owner request: "we need to do a full test on jev classification ... assuming
that there will be some other model handling extraction ... jp, zhcn,ko, then
the next top 3 languages in our db."

- Reuse `experiment/post-interpretation`; preserve all existing dirty files.
- No application edits, database writes, X-provider calls, harvest execution,
  scheduler changes, commits, deployment, or production activation.
- At most eight read-only database requests, each <=45 seconds database time;
  one database query at a time. Retain SQL and receipts before further queries.
- Select the other three languages from a saved all-date database census after
  excluding Japanese, all Chinese variants, Korean, and unknown language codes.
  Prefer detected language, falling back to provider language; preserve both.
  Generic `zh` does not establish Simplified Chinese: manually verify the script
  in selected Chinese posts and report ambiguous/traditional exclusions.
- Intended cohort: 12 deterministic natural-sample posts per language plus
  up to 8 distinct coverage/challenge posts per language (maximum 120 posts).
  Cover every classifier label through real posts where available; publish
  missing positive-label support as untested, not passed. No synthetic fill.
- Full classification scope: outcome, 14 post types, 7 audience topics,
  5 product labels, sentiment, 3 geopolitical modes, China/US stance, and
  5 untracked-promotion flags. Preserve exclusive none/unavailable/residual
  meanings and multiple simultaneously supported labels.
- Extraction boundary: source and stored brand/account evidence are available;
  Jev must not output names, domains, handles, quotations, dates, jobs, or events.
  This does not measure the accuracy/cost of a future extraction model.
- At most 240 Jev calls, pinned `jev-1.13.0`, sequential, zero retries.
  One source-language arm and one source-plus-existing-English-translation arm
  per non-English post; English posts need only one identical-input control.
  Missing translations are reported, not generated or silently substituted.
- Model-spend ceiling US$0.50, at published US$0.042/M input tokens; output free.
  Reserve conservative request cost before each call; stop on transport/HTTP
  uncertainty or budget. Retain malformed semantic fields as failures without
  reissuing the request. No question/threshold tuning after scores are visible.
- One fixed pass. No 0731 comparison calls or extractor calls in this run.
- Results are a development diagnostic, not independent human-adjudicated
  production accuracy or proof that confidence estimates are calibrated.

## Pre-inference completion requirements

Save the census and selection provenance, exact cohort, expected classifications,
question definitions, scoring/consistency rules, permitted input fields, and
hashes before the first Jev call. Add the final contract with denominators and
any scope amendments before inference, not after inspecting model answers.
